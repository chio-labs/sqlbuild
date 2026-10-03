//! Relation marker calls read from a parsed statement's serialized shape without a JSON tree.

use std::cell::RefCell;

use serde::Serialize;
use serde::ser::{
    self, SerializeMap, SerializeSeq, SerializeStruct, SerializeStructVariant, SerializeTuple,
    SerializeTupleStruct, SerializeTupleVariant,
};

use crate::compiler::_helpers::sql_tests::errors::RelationMarkerError;
use crate::compiler::_helpers::sql_tests::planning::DBT_REF_FUNCTION;

pub(crate) type MarkerCall = (String, String);

/// Return the marker relations a walk of `serde_json::to_value(value)` finds, in the same order.
pub(crate) fn relation_marker_calls<T: Serialize + ?Sized>(value: &T) -> Result<Vec<MarkerCall>> {
    let stack: RefCell<Vec<(Key, Out)>> = RefCell::new(Vec::new());
    let out = value.serialize(Collector {
        need: Need::Walk,
        stack: &stack,
    })?;
    Ok(out.calls)
}

/// What the parent reads from a value besides the marker calls found beneath it.
#[derive(Clone, Copy, PartialEq, Eq)]
enum Need {
    Walk,
    From,
    FromExpressions,
    Joins,
    Marker,
    ThisMarker,
    Function,
    Args,
    Arg,
    Column,
    Name,
    Str,
}

impl Need {
    fn field(self, key: &str) -> Need {
        match (self, key) {
            (_, "from") => Need::From,
            (_, "joins") => Need::Joins,
            (Need::From, "expressions") => Need::FromExpressions,
            (Need::Marker, "alias") => Need::ThisMarker,
            (Need::Marker, "function") => Need::Function,
            (Need::ThisMarker, "this") => Need::Marker,
            (Need::Function, "name") | (Need::Name, "name") => Need::Str,
            (Need::Function, "args") => Need::Args,
            (Need::Arg, "column") => Need::Column,
            (Need::Column, "name") => Need::Name,
            _ => Need::Walk,
        }
    }

    fn element(self) -> Need {
        match self {
            Need::FromExpressions => Need::Marker,
            Need::Joins => Need::ThisMarker,
            Need::Args => Need::Arg,
            _ => Need::Walk,
        }
    }
}

#[derive(Default)]
enum Info {
    #[default]
    None,
    Str(String),
    Marker(MarkerCall),
    Markers(Vec<Option<MarkerCall>>),
    Names(Vec<Option<String>>),
    Function(Option<String>, Option<Vec<Option<String>>>),
}

impl Info {
    fn into_str(self) -> Option<String> {
        match self {
            Info::Str(value) => Some(value),
            _ => None,
        }
    }

    fn into_marker(self) -> Option<MarkerCall> {
        match self {
            Info::Marker(value) => Some(value),
            _ => None,
        }
    }
}

#[derive(Default)]
struct Out {
    calls: Vec<MarkerCall>,
    info: Info,
}

impl Out {
    fn leaf() -> Self {
        Self::default()
    }
}

type Result<T> = std::result::Result<T, RelationMarkerError>;

enum Key {
    Static(&'static str),
    Owned(String),
}

impl Key {
    fn as_str(&self) -> &str {
        match self {
            Key::Static(value) => value,
            Key::Owned(value) => value,
        }
    }
}

type Stack = RefCell<Vec<(Key, Out)>>;

/// Pop the entries pushed since `start` as one object; a repeated key keeps its first position.
fn finish_object(need: Need, stack: &Stack, start: usize, may_repeat_keys: bool) -> Out {
    let mut stack = stack.borrow_mut();
    let mut index = start + 1;
    while may_repeat_keys && index < stack.len() {
        let name = stack[index].0.as_str();
        match stack[start..index]
            .iter()
            .position(|(key, _)| key.as_str() == name)
        {
            Some(first) => {
                let (_, out) = stack.remove(index);
                stack[start + first].1 = out;
            }
            None => index += 1,
        }
    }
    let entries = &mut stack[start..];
    let mut take = |name: &str| -> Option<Info> {
        entries
            .iter_mut()
            .find(|(key, _)| key.as_str() == name)
            .map(|(_, out)| std::mem::take(&mut out.info))
    };
    let mut calls: Vec<MarkerCall> = Vec::new();
    for name in ["from", "joins"] {
        if let Some(Info::Markers(markers)) = take(name) {
            calls.extend(markers.into_iter().flatten());
        }
    }
    let info = match need {
        Need::Marker => match take("alias") {
            Some(alias) => alias.into_marker().map_or(Info::None, Info::Marker),
            None => match take("function") {
                Some(Info::Function(Some(name), Some(args))) => {
                    function_marker(&name, args).map_or(Info::None, Info::Marker)
                }
                _ => Info::None,
            },
        },
        Need::ThisMarker => take("this").unwrap_or_default(),
        Need::From => match take("expressions") {
            Some(markers @ Info::Markers(_)) => markers,
            _ => Info::None,
        },
        Need::Function => Info::Function(
            take("name").and_then(Info::into_str),
            match take("args") {
                Some(Info::Names(names)) => Some(names),
                _ => None,
            },
        ),
        Need::Arg => take("column").unwrap_or_default(),
        Need::Column | Need::Name => take("name").unwrap_or_default(),
        Need::Walk | Need::FromExpressions | Need::Joins | Need::Args | Need::Str => Info::None,
    };
    for (_, out) in stack.drain(start..) {
        calls.extend(out.calls);
    }
    Out { calls, info }
}

/// One bit per key shape, so repeated keys are checked exactly only when a bit repeats.
fn key_bit(key: &str) -> u64 {
    let bytes = key.as_bytes();
    let shape = bytes.len()
        ^ usize::from(bytes.first().copied().unwrap_or(0)).rotate_left(3)
        ^ usize::from(bytes.last().copied().unwrap_or(0)).rotate_left(7);
    1u64 << (shape % 64)
}

fn function_marker(name: &str, args: Vec<Option<String>>) -> Option<MarkerCall> {
    let function_name = name.to_ascii_lowercase();
    let referenced_name = if function_name == DBT_REF_FUNCTION {
        match args.as_slice() {
            [Some(first)] => first.clone(),
            [Some(first), Some(second)] => format!("{first}__{second}"),
            _ => return None,
        }
    } else {
        let [Some(first)] = args.as_slice() else {
            return None;
        };
        first.clone()
    };
    Some((function_name, referenced_name))
}

fn finish_array(need: Need, stack: &Stack, start: usize) -> Out {
    let mut calls: Vec<MarkerCall> = Vec::new();
    let mut stack = stack.borrow_mut();
    let info = match need {
        Need::FromExpressions | Need::Joins => Info::Markers(
            stack[start..]
                .iter_mut()
                .map(|(_, out)| std::mem::take(&mut out.info).into_marker())
                .collect(),
        ),
        Need::Args => Info::Names(
            stack[start..]
                .iter_mut()
                .map(|(_, out)| std::mem::take(&mut out.info).into_str())
                .collect(),
        ),
        _ => Info::None,
    };
    for (_, out) in stack.drain(start..) {
        calls.extend(out.calls);
    }
    Out { calls, info }
}

#[derive(Clone, Copy)]
struct Collector<'a> {
    need: Need,
    stack: &'a Stack,
}

impl<'a> Collector<'a> {
    fn string(self, value: impl FnOnce() -> String) -> Out {
        Out {
            calls: Vec::new(),
            info: if self.need == Need::Str {
                Info::Str(value())
            } else {
                Info::None
            },
        }
    }

    fn array(self, need: Need) -> ArrayFrame<'a> {
        ArrayFrame {
            need,
            stack: self.stack,
            start: self.stack.borrow().len(),
        }
    }

    /// Open `{variant: payload}`; the outer object is empty until the payload closes.
    fn variant<F>(
        self,
        variant: &'static str,
        payload: fn(Self, Need) -> F,
    ) -> VariantFrame<'a, F> {
        VariantFrame {
            outer: self.object(self.need),
            variant,
            inner: payload(self, self.need.field(variant)),
        }
    }

    fn object(self, need: Need) -> ObjectFrame<'a> {
        ObjectFrame {
            need,
            stack: self.stack,
            start: self.stack.borrow().len(),
            key_bits: 0,
            may_repeat_keys: false,
            pending_key: None,
        }
    }
}

struct ArrayFrame<'a> {
    need: Need,
    stack: &'a Stack,
    start: usize,
}

impl ArrayFrame<'_> {
    fn push<T: Serialize + ?Sized>(&mut self, value: &T) -> Result<()> {
        let out = value.serialize(Collector {
            need: self.need.element(),
            stack: self.stack,
        })?;
        self.stack.borrow_mut().push((Key::Static(""), out));
        Ok(())
    }

    fn finish(self) -> Out {
        finish_array(self.need, self.stack, self.start)
    }
}

struct ObjectFrame<'a> {
    need: Need,
    stack: &'a Stack,
    start: usize,
    key_bits: u64,
    may_repeat_keys: bool,
    pending_key: Option<Key>,
}

impl ObjectFrame<'_> {
    fn push<T: Serialize + ?Sized>(&mut self, key: Key, value: &T) -> Result<()> {
        let out = value.serialize(Collector {
            need: self.need.field(key.as_str()),
            stack: self.stack,
        })?;
        let bit = key_bit(key.as_str());
        self.may_repeat_keys |= self.key_bits & bit != 0;
        self.key_bits |= bit;
        self.stack.borrow_mut().push((key, out));
        Ok(())
    }

    fn finish(self) -> Out {
        finish_object(self.need, self.stack, self.start, self.may_repeat_keys)
    }
}

/// A variant wrapper object `{variant: inner}` around an array or object payload.
struct VariantFrame<'a, F> {
    outer: ObjectFrame<'a>,
    variant: &'static str,
    inner: F,
}

impl<F> VariantFrame<'_, F> {
    fn finish(self, inner: Out) -> Out {
        let outer = self.outer;
        outer
            .stack
            .borrow_mut()
            .push((Key::Static(self.variant), inner));
        outer.finish()
    }
}

impl<'a> ser::Serializer for Collector<'a> {
    type Ok = Out;
    type Error = RelationMarkerError;
    type SerializeSeq = ArrayFrame<'a>;
    type SerializeTuple = ArrayFrame<'a>;
    type SerializeTupleStruct = ArrayFrame<'a>;
    type SerializeTupleVariant = VariantFrame<'a, ArrayFrame<'a>>;
    type SerializeMap = ObjectFrame<'a>;
    type SerializeStruct = ObjectFrame<'a>;
    type SerializeStructVariant = VariantFrame<'a, ObjectFrame<'a>>;

    fn serialize_bool(self, _value: bool) -> Result<Out> {
        Ok(Out::leaf())
    }

    fn serialize_i8(self, _value: i8) -> Result<Out> {
        Ok(Out::leaf())
    }

    fn serialize_i16(self, _value: i16) -> Result<Out> {
        Ok(Out::leaf())
    }

    fn serialize_i32(self, _value: i32) -> Result<Out> {
        Ok(Out::leaf())
    }

    fn serialize_i64(self, _value: i64) -> Result<Out> {
        Ok(Out::leaf())
    }

    fn serialize_i128(self, value: i128) -> Result<Out> {
        if (i128::from(i64::MIN)..=i128::from(u64::MAX)).contains(&value) {
            Ok(Out::leaf())
        } else {
            Err(RelationMarkerError)
        }
    }

    fn serialize_u8(self, _value: u8) -> Result<Out> {
        Ok(Out::leaf())
    }

    fn serialize_u16(self, _value: u16) -> Result<Out> {
        Ok(Out::leaf())
    }

    fn serialize_u32(self, _value: u32) -> Result<Out> {
        Ok(Out::leaf())
    }

    fn serialize_u64(self, _value: u64) -> Result<Out> {
        Ok(Out::leaf())
    }

    fn serialize_u128(self, value: u128) -> Result<Out> {
        if value <= u128::from(u64::MAX) {
            Ok(Out::leaf())
        } else {
            Err(RelationMarkerError)
        }
    }

    fn serialize_f32(self, _value: f32) -> Result<Out> {
        Ok(Out::leaf())
    }

    fn serialize_f64(self, _value: f64) -> Result<Out> {
        Ok(Out::leaf())
    }

    fn serialize_char(self, value: char) -> Result<Out> {
        Ok(self.string(|| value.to_string()))
    }

    fn serialize_str(self, value: &str) -> Result<Out> {
        Ok(self.string(|| value.to_string()))
    }

    fn serialize_bytes(self, _value: &[u8]) -> Result<Out> {
        Ok(Out::leaf())
    }

    fn serialize_none(self) -> Result<Out> {
        Ok(Out::leaf())
    }

    fn serialize_some<T: Serialize + ?Sized>(self, value: &T) -> Result<Out> {
        value.serialize(self)
    }

    fn serialize_unit(self) -> Result<Out> {
        Ok(Out::leaf())
    }

    fn serialize_unit_struct(self, _name: &'static str) -> Result<Out> {
        Ok(Out::leaf())
    }

    fn serialize_unit_variant(
        self,
        _name: &'static str,
        _variant_index: u32,
        variant: &'static str,
    ) -> Result<Out> {
        Ok(self.string(|| variant.to_string()))
    }

    fn serialize_newtype_struct<T: Serialize + ?Sized>(
        self,
        _name: &'static str,
        value: &T,
    ) -> Result<Out> {
        value.serialize(self)
    }

    fn serialize_newtype_variant<T: Serialize + ?Sized>(
        self,
        _name: &'static str,
        _variant_index: u32,
        variant: &'static str,
        value: &T,
    ) -> Result<Out> {
        let mut frame = self.object(self.need);
        frame.push(Key::Static(variant), value)?;
        Ok(frame.finish())
    }

    fn serialize_seq(self, _len: Option<usize>) -> Result<ArrayFrame<'a>> {
        Ok(self.array(self.need))
    }

    fn serialize_tuple(self, _len: usize) -> Result<ArrayFrame<'a>> {
        Ok(self.array(self.need))
    }

    fn serialize_tuple_struct(self, _name: &'static str, _len: usize) -> Result<ArrayFrame<'a>> {
        Ok(self.array(self.need))
    }

    fn serialize_tuple_variant(
        self,
        _name: &'static str,
        _variant_index: u32,
        variant: &'static str,
        _len: usize,
    ) -> Result<VariantFrame<'a, ArrayFrame<'a>>> {
        Ok(self.variant(variant, Collector::array))
    }

    fn serialize_map(self, _len: Option<usize>) -> Result<ObjectFrame<'a>> {
        Ok(self.object(self.need))
    }

    fn serialize_struct(self, _name: &'static str, _len: usize) -> Result<ObjectFrame<'a>> {
        Ok(self.object(self.need))
    }

    fn serialize_struct_variant(
        self,
        _name: &'static str,
        _variant_index: u32,
        variant: &'static str,
        _len: usize,
    ) -> Result<VariantFrame<'a, ObjectFrame<'a>>> {
        Ok(self.variant(variant, Collector::object))
    }
}

impl SerializeSeq for ArrayFrame<'_> {
    type Ok = Out;
    type Error = RelationMarkerError;

    fn serialize_element<T: Serialize + ?Sized>(&mut self, value: &T) -> Result<()> {
        self.push(value)
    }

    fn end(self) -> Result<Out> {
        Ok(self.finish())
    }
}

impl SerializeTuple for ArrayFrame<'_> {
    type Ok = Out;
    type Error = RelationMarkerError;

    fn serialize_element<T: Serialize + ?Sized>(&mut self, value: &T) -> Result<()> {
        self.push(value)
    }

    fn end(self) -> Result<Out> {
        Ok(self.finish())
    }
}

impl SerializeTupleStruct for ArrayFrame<'_> {
    type Ok = Out;
    type Error = RelationMarkerError;

    fn serialize_field<T: Serialize + ?Sized>(&mut self, value: &T) -> Result<()> {
        self.push(value)
    }

    fn end(self) -> Result<Out> {
        Ok(self.finish())
    }
}

impl SerializeTupleVariant for VariantFrame<'_, ArrayFrame<'_>> {
    type Ok = Out;
    type Error = RelationMarkerError;

    fn serialize_field<T: Serialize + ?Sized>(&mut self, value: &T) -> Result<()> {
        self.inner.push(value)
    }

    fn end(self) -> Result<Out> {
        let inner = finish_array(self.inner.need, self.inner.stack, self.inner.start);
        Ok(self.finish(inner))
    }
}

impl SerializeMap for ObjectFrame<'_> {
    type Ok = Out;
    type Error = RelationMarkerError;

    fn serialize_key<T: Serialize + ?Sized>(&mut self, key: &T) -> Result<()> {
        self.pending_key = Some(Key::Owned(key.serialize(MapKeyCollector)?));
        Ok(())
    }

    fn serialize_value<T: Serialize + ?Sized>(&mut self, value: &T) -> Result<()> {
        let key = self.pending_key.take().ok_or(RelationMarkerError)?;
        self.push(key, value)
    }

    fn end(self) -> Result<Out> {
        Ok(self.finish())
    }
}

impl SerializeStruct for ObjectFrame<'_> {
    type Ok = Out;
    type Error = RelationMarkerError;

    fn serialize_field<T: Serialize + ?Sized>(
        &mut self,
        key: &'static str,
        value: &T,
    ) -> Result<()> {
        self.push(Key::Static(key), value)
    }

    fn end(self) -> Result<Out> {
        Ok(self.finish())
    }
}

impl SerializeStructVariant for VariantFrame<'_, ObjectFrame<'_>> {
    type Ok = Out;
    type Error = RelationMarkerError;

    fn serialize_field<T: Serialize + ?Sized>(
        &mut self,
        key: &'static str,
        value: &T,
    ) -> Result<()> {
        self.inner.push(Key::Static(key), value)
    }

    fn end(self) -> Result<Out> {
        let inner = finish_object(
            self.inner.need,
            self.inner.stack,
            self.inner.start,
            self.inner.may_repeat_keys,
        );
        Ok(self.finish(inner))
    }
}

/// Map keys as `serde_json` stringifies them; unsupported key types fail as they do there.
struct MapKeyCollector;

impl ser::Serializer for MapKeyCollector {
    type Ok = String;
    type Error = RelationMarkerError;
    type SerializeSeq = ser::Impossible<String, RelationMarkerError>;
    type SerializeTuple = ser::Impossible<String, RelationMarkerError>;
    type SerializeTupleStruct = ser::Impossible<String, RelationMarkerError>;
    type SerializeTupleVariant = ser::Impossible<String, RelationMarkerError>;
    type SerializeMap = ser::Impossible<String, RelationMarkerError>;
    type SerializeStruct = ser::Impossible<String, RelationMarkerError>;
    type SerializeStructVariant = ser::Impossible<String, RelationMarkerError>;

    fn serialize_bool(self, value: bool) -> Result<String> {
        Ok(value.to_string())
    }

    fn serialize_i8(self, value: i8) -> Result<String> {
        Ok(value.to_string())
    }

    fn serialize_i16(self, value: i16) -> Result<String> {
        Ok(value.to_string())
    }

    fn serialize_i32(self, value: i32) -> Result<String> {
        Ok(value.to_string())
    }

    fn serialize_i64(self, value: i64) -> Result<String> {
        Ok(value.to_string())
    }

    fn serialize_i128(self, value: i128) -> Result<String> {
        Ok(value.to_string())
    }

    fn serialize_u8(self, value: u8) -> Result<String> {
        Ok(value.to_string())
    }

    fn serialize_u16(self, value: u16) -> Result<String> {
        Ok(value.to_string())
    }

    fn serialize_u32(self, value: u32) -> Result<String> {
        Ok(value.to_string())
    }

    fn serialize_u64(self, value: u64) -> Result<String> {
        Ok(value.to_string())
    }

    fn serialize_u128(self, value: u128) -> Result<String> {
        Ok(value.to_string())
    }

    fn serialize_f32(self, value: f32) -> Result<String> {
        if value.is_finite() {
            Ok(format!("{value:?}"))
        } else {
            Err(RelationMarkerError)
        }
    }

    fn serialize_f64(self, value: f64) -> Result<String> {
        if value.is_finite() {
            Ok(format!("{value:?}"))
        } else {
            Err(RelationMarkerError)
        }
    }

    fn serialize_char(self, value: char) -> Result<String> {
        Ok(value.to_string())
    }

    fn serialize_str(self, value: &str) -> Result<String> {
        Ok(value.to_string())
    }

    fn serialize_bytes(self, _value: &[u8]) -> Result<String> {
        Err(RelationMarkerError)
    }

    fn serialize_none(self) -> Result<String> {
        Err(RelationMarkerError)
    }

    fn serialize_some<T: Serialize + ?Sized>(self, _value: &T) -> Result<String> {
        Err(RelationMarkerError)
    }

    fn serialize_unit(self) -> Result<String> {
        Err(RelationMarkerError)
    }

    fn serialize_unit_struct(self, _name: &'static str) -> Result<String> {
        Err(RelationMarkerError)
    }

    fn serialize_unit_variant(
        self,
        _name: &'static str,
        _variant_index: u32,
        variant: &'static str,
    ) -> Result<String> {
        Ok(variant.to_string())
    }

    fn serialize_newtype_struct<T: Serialize + ?Sized>(
        self,
        _name: &'static str,
        value: &T,
    ) -> Result<String> {
        value.serialize(self)
    }

    fn serialize_newtype_variant<T: Serialize + ?Sized>(
        self,
        _name: &'static str,
        _variant_index: u32,
        _variant: &'static str,
        _value: &T,
    ) -> Result<String> {
        Err(RelationMarkerError)
    }

    fn serialize_seq(self, _len: Option<usize>) -> Result<Self::SerializeSeq> {
        Err(RelationMarkerError)
    }

    fn serialize_tuple(self, _len: usize) -> Result<Self::SerializeTuple> {
        Err(RelationMarkerError)
    }

    fn serialize_tuple_struct(
        self,
        _name: &'static str,
        _len: usize,
    ) -> Result<Self::SerializeTupleStruct> {
        Err(RelationMarkerError)
    }

    fn serialize_tuple_variant(
        self,
        _name: &'static str,
        _variant_index: u32,
        _variant: &'static str,
        _len: usize,
    ) -> Result<Self::SerializeTupleVariant> {
        Err(RelationMarkerError)
    }

    fn serialize_map(self, _len: Option<usize>) -> Result<Self::SerializeMap> {
        Err(RelationMarkerError)
    }

    fn serialize_struct(self, _name: &'static str, _len: usize) -> Result<Self::SerializeStruct> {
        Err(RelationMarkerError)
    }

    fn serialize_struct_variant(
        self,
        _name: &'static str,
        _variant_index: u32,
        _variant: &'static str,
        _len: usize,
    ) -> Result<Self::SerializeStructVariant> {
        Err(RelationMarkerError)
    }
}
