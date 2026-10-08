//! The shape the wheel's `to_dict` gives an expression: pythonize's dicts, lists and tuples.

use serde::ser::{
    Serialize, SerializeMap, SerializeSeq, SerializeStruct, SerializeStructVariant, SerializeTuple,
    SerializeTupleStruct, SerializeTupleVariant, Serializer,
};

use crate::lineage::errors::PayloadError;

/// A Python value as pythonize builds it, keeping only what the lineage walk reads.
#[derive(Debug, Clone, PartialEq)]
pub(crate) enum PythonValue {
    /// Entries in insertion order; `None` keys are not strings.
    Dict(Vec<(Option<String>, PythonValue)>),
    List(Vec<PythonValue>),
    /// Serde tuples, tuple structs and tuple variant bodies, which pythonize makes Python tuples.
    Tuple(Vec<PythonValue>),
    Str(String),
    Scalar,
}

impl PythonValue {
    /// Python's `dict.get` for a string key.
    pub(crate) fn get(&self, key: &str) -> Option<&PythonValue> {
        let PythonValue::Dict(entries) = self else {
            return None;
        };
        entries
            .iter()
            .find(|(name, _)| name.as_deref() == Some(key))
            .map(|(_, value)| value)
    }
}

/// The value pythonize would build for `value`.
pub(crate) fn python_payload<T: Serialize + ?Sized>(
    value: &T,
) -> Result<PythonValue, PayloadError> {
    value.serialize(PayloadSerializer)
}

fn variant(name: &str, value: PythonValue) -> PythonValue {
    PythonValue::Dict(vec![(Some(name.to_owned()), value)])
}

struct PayloadSerializer;

struct Collection {
    tuple: bool,
    items: Vec<PythonValue>,
}

impl Collection {
    fn finish(self) -> PythonValue {
        if self.tuple {
            PythonValue::Tuple(self.items)
        } else {
            PythonValue::List(self.items)
        }
    }
}

struct TupleVariant {
    name: &'static str,
    items: Vec<PythonValue>,
}

struct Dict {
    entries: Vec<(Option<String>, PythonValue)>,
    key: Option<Option<String>>,
}

impl Dict {
    fn with_capacity(length: usize) -> Self {
        Self {
            entries: Vec::with_capacity(length),
            key: None,
        }
    }

    /// Python's dictionary assignment: an existing string key keeps its position.
    fn assign(&mut self, key: Option<String>, value: PythonValue) {
        let existing: Option<usize> = key.as_deref().and_then(|name| {
            self.entries
                .iter()
                .position(|(other, _)| other.as_deref() == Some(name))
        });
        match existing {
            Some(index) => self.entries[index].1 = value,
            None => self.entries.push((key, value)),
        }
    }
}

struct StructVariant {
    name: &'static str,
    dict: Dict,
}

impl Serializer for PayloadSerializer {
    type Ok = PythonValue;
    type Error = PayloadError;
    type SerializeSeq = Collection;
    type SerializeTuple = Collection;
    type SerializeTupleStruct = Collection;
    type SerializeTupleVariant = TupleVariant;
    type SerializeMap = Dict;
    type SerializeStruct = Dict;
    type SerializeStructVariant = StructVariant;

    fn serialize_bool(self, _: bool) -> Result<PythonValue, PayloadError> {
        Ok(PythonValue::Scalar)
    }
    fn serialize_i8(self, _: i8) -> Result<PythonValue, PayloadError> {
        Ok(PythonValue::Scalar)
    }
    fn serialize_i16(self, _: i16) -> Result<PythonValue, PayloadError> {
        Ok(PythonValue::Scalar)
    }
    fn serialize_i32(self, _: i32) -> Result<PythonValue, PayloadError> {
        Ok(PythonValue::Scalar)
    }
    fn serialize_i64(self, _: i64) -> Result<PythonValue, PayloadError> {
        Ok(PythonValue::Scalar)
    }
    fn serialize_u8(self, _: u8) -> Result<PythonValue, PayloadError> {
        Ok(PythonValue::Scalar)
    }
    fn serialize_u16(self, _: u16) -> Result<PythonValue, PayloadError> {
        Ok(PythonValue::Scalar)
    }
    fn serialize_u32(self, _: u32) -> Result<PythonValue, PayloadError> {
        Ok(PythonValue::Scalar)
    }
    fn serialize_u64(self, _: u64) -> Result<PythonValue, PayloadError> {
        Ok(PythonValue::Scalar)
    }
    fn serialize_f32(self, _: f32) -> Result<PythonValue, PayloadError> {
        Ok(PythonValue::Scalar)
    }
    fn serialize_f64(self, _: f64) -> Result<PythonValue, PayloadError> {
        Ok(PythonValue::Scalar)
    }
    fn serialize_char(self, value: char) -> Result<PythonValue, PayloadError> {
        Ok(PythonValue::Str(value.to_string()))
    }
    fn serialize_str(self, value: &str) -> Result<PythonValue, PayloadError> {
        Ok(PythonValue::Str(value.to_owned()))
    }
    fn serialize_bytes(self, _: &[u8]) -> Result<PythonValue, PayloadError> {
        Ok(PythonValue::Scalar)
    }
    fn serialize_none(self) -> Result<PythonValue, PayloadError> {
        Ok(PythonValue::Scalar)
    }
    fn serialize_some<T: Serialize + ?Sized>(self, value: &T) -> Result<PythonValue, PayloadError> {
        value.serialize(self)
    }
    fn serialize_unit(self) -> Result<PythonValue, PayloadError> {
        Ok(PythonValue::Scalar)
    }
    fn serialize_unit_struct(self, _: &'static str) -> Result<PythonValue, PayloadError> {
        Ok(PythonValue::Scalar)
    }
    fn serialize_unit_variant(
        self,
        _: &'static str,
        _: u32,
        name: &'static str,
    ) -> Result<PythonValue, PayloadError> {
        Ok(PythonValue::Str(name.to_owned()))
    }
    fn serialize_newtype_struct<T: Serialize + ?Sized>(
        self,
        _: &'static str,
        value: &T,
    ) -> Result<PythonValue, PayloadError> {
        value.serialize(self)
    }
    fn serialize_newtype_variant<T: Serialize + ?Sized>(
        self,
        _: &'static str,
        _: u32,
        name: &'static str,
        value: &T,
    ) -> Result<PythonValue, PayloadError> {
        Ok(variant(name, value.serialize(PayloadSerializer)?))
    }
    fn serialize_seq(self, length: Option<usize>) -> Result<Collection, PayloadError> {
        Ok(Collection {
            tuple: false,
            items: Vec::with_capacity(length.unwrap_or(0)),
        })
    }
    fn serialize_tuple(self, length: usize) -> Result<Collection, PayloadError> {
        Ok(Collection {
            tuple: true,
            items: Vec::with_capacity(length),
        })
    }
    fn serialize_tuple_struct(
        self,
        _: &'static str,
        length: usize,
    ) -> Result<Collection, PayloadError> {
        self.serialize_tuple(length)
    }
    fn serialize_tuple_variant(
        self,
        _: &'static str,
        _: u32,
        name: &'static str,
        length: usize,
    ) -> Result<TupleVariant, PayloadError> {
        Ok(TupleVariant {
            name,
            items: Vec::with_capacity(length),
        })
    }
    fn serialize_map(self, length: Option<usize>) -> Result<Dict, PayloadError> {
        Ok(Dict::with_capacity(length.unwrap_or(0)))
    }
    fn serialize_struct(self, _: &'static str, length: usize) -> Result<Dict, PayloadError> {
        Ok(Dict::with_capacity(length))
    }
    fn serialize_struct_variant(
        self,
        _: &'static str,
        _: u32,
        name: &'static str,
        length: usize,
    ) -> Result<StructVariant, PayloadError> {
        Ok(StructVariant {
            name,
            dict: Dict::with_capacity(length),
        })
    }
}

impl SerializeSeq for Collection {
    type Ok = PythonValue;
    type Error = PayloadError;
    fn serialize_element<T: Serialize + ?Sized>(&mut self, value: &T) -> Result<(), PayloadError> {
        self.items.push(value.serialize(PayloadSerializer)?);
        Ok(())
    }
    fn end(self) -> Result<PythonValue, PayloadError> {
        Ok(self.finish())
    }
}

impl SerializeTuple for Collection {
    type Ok = PythonValue;
    type Error = PayloadError;
    fn serialize_element<T: Serialize + ?Sized>(&mut self, value: &T) -> Result<(), PayloadError> {
        SerializeSeq::serialize_element(self, value)
    }
    fn end(self) -> Result<PythonValue, PayloadError> {
        Ok(self.finish())
    }
}

impl SerializeTupleStruct for Collection {
    type Ok = PythonValue;
    type Error = PayloadError;
    fn serialize_field<T: Serialize + ?Sized>(&mut self, value: &T) -> Result<(), PayloadError> {
        SerializeSeq::serialize_element(self, value)
    }
    fn end(self) -> Result<PythonValue, PayloadError> {
        Ok(self.finish())
    }
}

impl SerializeTupleVariant for TupleVariant {
    type Ok = PythonValue;
    type Error = PayloadError;
    fn serialize_field<T: Serialize + ?Sized>(&mut self, value: &T) -> Result<(), PayloadError> {
        self.items.push(value.serialize(PayloadSerializer)?);
        Ok(())
    }
    fn end(self) -> Result<PythonValue, PayloadError> {
        Ok(variant(self.name, PythonValue::Tuple(self.items)))
    }
}

impl SerializeMap for Dict {
    type Ok = PythonValue;
    type Error = PayloadError;
    fn serialize_key<T: Serialize + ?Sized>(&mut self, key: &T) -> Result<(), PayloadError> {
        let key = match key.serialize(PayloadSerializer)? {
            PythonValue::Str(name) => Some(name),
            _ => None,
        };
        self.key = Some(key);
        Ok(())
    }
    fn serialize_value<T: Serialize + ?Sized>(&mut self, value: &T) -> Result<(), PayloadError> {
        let Some(key) = self.key.take() else {
            return Err(PayloadError::new("map value without a key"));
        };
        self.assign(key, value.serialize(PayloadSerializer)?);
        Ok(())
    }
    fn end(self) -> Result<PythonValue, PayloadError> {
        Ok(PythonValue::Dict(self.entries))
    }
}

impl SerializeStruct for Dict {
    type Ok = PythonValue;
    type Error = PayloadError;
    fn serialize_field<T: Serialize + ?Sized>(
        &mut self,
        key: &'static str,
        value: &T,
    ) -> Result<(), PayloadError> {
        self.assign(Some(key.to_owned()), value.serialize(PayloadSerializer)?);
        Ok(())
    }
    fn end(self) -> Result<PythonValue, PayloadError> {
        Ok(PythonValue::Dict(self.entries))
    }
}

impl SerializeStructVariant for StructVariant {
    type Ok = PythonValue;
    type Error = PayloadError;
    fn serialize_field<T: Serialize + ?Sized>(
        &mut self,
        key: &'static str,
        value: &T,
    ) -> Result<(), PayloadError> {
        self.dict
            .assign(Some(key.to_owned()), value.serialize(PayloadSerializer)?);
        Ok(())
    }
    fn end(self) -> Result<PythonValue, PayloadError> {
        Ok(variant(self.name, PythonValue::Dict(self.dict.entries)))
    }
}
