//! The wheel's `DataType.args` scalars, read without walking nested types.
//!
//! Serializing a whole parsed type recurses once per nesting level; normalization only reads
//! the top-level tag, name and size parameters, so nested values are skipped unvisited.

use std::fmt::Display;

use serde::ser::{
    Impossible, Serialize, SerializeMap, SerializeSeq, SerializeStruct, SerializeStructVariant,
    SerializeTuple, SerializeTupleStruct, SerializeTupleVariant, Serializer,
};
use serde_json::{Map, Number, Value};

/// The top-level scalar fields of one serialized value; nested values are absent.
pub(crate) fn shallow_args<T: Serialize>(value: &T) -> Map<String, Value> {
    value.serialize(Fields::default()).unwrap_or_default()
}

#[derive(Debug)]
pub(crate) struct Unsupported;

impl Display for Unsupported {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str("not a struct")
    }
}

impl std::error::Error for Unsupported {}

impl serde::ser::Error for Unsupported {
    fn custom<T: Display>(_message: T) -> Self {
        Self
    }
}

/// Collects one struct's scalar fields.
#[derive(Default)]
struct Fields {
    fields: Map<String, Value>,
}

impl SerializeStruct for Fields {
    type Ok = Map<String, Value>;
    type Error = Unsupported;

    fn serialize_field<T: ?Sized + Serialize>(
        &mut self,
        key: &'static str,
        value: &T,
    ) -> Result<(), Unsupported> {
        if let Some(scalar) = value.serialize(Scalar)? {
            let _ = self.fields.insert(key.to_owned(), scalar);
        }
        Ok(())
    }

    fn end(self) -> Result<Map<String, Value>, Unsupported> {
        Ok(self.fields)
    }
}

impl SerializeStructVariant for Fields {
    type Ok = Map<String, Value>;
    type Error = Unsupported;

    fn serialize_field<T: ?Sized + Serialize>(
        &mut self,
        key: &'static str,
        value: &T,
    ) -> Result<(), Unsupported> {
        SerializeStruct::serialize_field(self, key, value)
    }

    fn end(self) -> Result<Map<String, Value>, Unsupported> {
        Ok(self.fields)
    }
}

impl SerializeMap for Fields {
    type Ok = Map<String, Value>;
    type Error = Unsupported;

    fn serialize_key<T: ?Sized + Serialize>(&mut self, _key: &T) -> Result<(), Unsupported> {
        Err(Unsupported)
    }

    fn serialize_value<T: ?Sized + Serialize>(&mut self, _value: &T) -> Result<(), Unsupported> {
        Err(Unsupported)
    }

    fn end(self) -> Result<Map<String, Value>, Unsupported> {
        Ok(self.fields)
    }
}

macro_rules! not_a_struct {
    ($($method:ident($($argument:ty),*)),* $(,)?) => {
        $(fn $method(self, $(_: $argument),*) -> Result<Self::Ok, Self::Error> {
            Err(Unsupported)
        })*
    };
}

impl Serializer for Fields {
    type Ok = Map<String, Value>;
    type Error = Unsupported;
    type SerializeSeq = Impossible<Self::Ok, Unsupported>;
    type SerializeTuple = Impossible<Self::Ok, Unsupported>;
    type SerializeTupleStruct = Impossible<Self::Ok, Unsupported>;
    type SerializeTupleVariant = Impossible<Self::Ok, Unsupported>;
    type SerializeMap = Self;
    type SerializeStruct = Self;
    type SerializeStructVariant = Self;

    not_a_struct!(
        serialize_bool(bool),
        serialize_i8(i8),
        serialize_i16(i16),
        serialize_i32(i32),
        serialize_i64(i64),
        serialize_u8(u8),
        serialize_u16(u16),
        serialize_u32(u32),
        serialize_u64(u64),
        serialize_f32(f32),
        serialize_f64(f64),
        serialize_char(char),
        serialize_str(&str),
        serialize_bytes(&[u8]),
        serialize_none(),
        serialize_unit(),
        serialize_unit_struct(&'static str),
        serialize_unit_variant(&'static str, u32, &'static str),
    );

    fn serialize_some<T: ?Sized + Serialize>(self, value: &T) -> Result<Self::Ok, Unsupported> {
        value.serialize(self)
    }

    fn serialize_newtype_struct<T: ?Sized + Serialize>(
        self,
        _name: &'static str,
        value: &T,
    ) -> Result<Self::Ok, Unsupported> {
        value.serialize(self)
    }

    fn serialize_newtype_variant<T: ?Sized + Serialize>(
        self,
        _name: &'static str,
        _index: u32,
        _variant: &'static str,
        _value: &T,
    ) -> Result<Self::Ok, Unsupported> {
        Err(Unsupported)
    }

    fn serialize_seq(self, _len: Option<usize>) -> Result<Self::SerializeSeq, Unsupported> {
        Err(Unsupported)
    }

    fn serialize_tuple(self, _len: usize) -> Result<Self::SerializeTuple, Unsupported> {
        Err(Unsupported)
    }

    fn serialize_tuple_struct(
        self,
        _name: &'static str,
        _len: usize,
    ) -> Result<Self::SerializeTupleStruct, Unsupported> {
        Err(Unsupported)
    }

    fn serialize_tuple_variant(
        self,
        _name: &'static str,
        _index: u32,
        _variant: &'static str,
        _len: usize,
    ) -> Result<Self::SerializeTupleVariant, Unsupported> {
        Err(Unsupported)
    }

    fn serialize_map(self, _len: Option<usize>) -> Result<Self::SerializeMap, Unsupported> {
        Ok(self)
    }

    fn serialize_struct(
        self,
        _name: &'static str,
        _len: usize,
    ) -> Result<Self::SerializeStruct, Unsupported> {
        Ok(self)
    }

    fn serialize_struct_variant(
        self,
        _name: &'static str,
        _index: u32,
        _variant: &'static str,
        _len: usize,
    ) -> Result<Self::SerializeStructVariant, Unsupported> {
        Ok(self)
    }
}

/// One field's value if it is a scalar; nested values are skipped without visiting them.
struct Scalar;

/// Swallows the children of a nested value unvisited.
struct Skipped;

macro_rules! skip_children {
    ($($trait:ident :: $method:ident),* $(,)?) => {
        $(impl $trait for Skipped {
            type Ok = Option<Value>;
            type Error = Unsupported;

            fn $method<T: ?Sized + Serialize>(&mut self, _value: &T) -> Result<(), Unsupported> {
                Ok(())
            }

            fn end(self) -> Result<Option<Value>, Unsupported> {
                Ok(None)
            }
        })*
    };
}

skip_children!(
    SerializeSeq::serialize_element,
    SerializeTuple::serialize_element,
    SerializeTupleStruct::serialize_field,
    SerializeTupleVariant::serialize_field,
);

impl SerializeMap for Skipped {
    type Ok = Option<Value>;
    type Error = Unsupported;

    fn serialize_key<T: ?Sized + Serialize>(&mut self, _key: &T) -> Result<(), Unsupported> {
        Ok(())
    }

    fn serialize_value<T: ?Sized + Serialize>(&mut self, _value: &T) -> Result<(), Unsupported> {
        Ok(())
    }

    fn end(self) -> Result<Option<Value>, Unsupported> {
        Ok(None)
    }
}

impl SerializeStruct for Skipped {
    type Ok = Option<Value>;
    type Error = Unsupported;

    fn serialize_field<T: ?Sized + Serialize>(
        &mut self,
        _key: &'static str,
        _value: &T,
    ) -> Result<(), Unsupported> {
        Ok(())
    }

    fn end(self) -> Result<Option<Value>, Unsupported> {
        Ok(None)
    }
}

impl SerializeStructVariant for Skipped {
    type Ok = Option<Value>;
    type Error = Unsupported;

    fn serialize_field<T: ?Sized + Serialize>(
        &mut self,
        _key: &'static str,
        _value: &T,
    ) -> Result<(), Unsupported> {
        Ok(())
    }

    fn end(self) -> Result<Option<Value>, Unsupported> {
        Ok(None)
    }
}

fn number(value: impl Into<Number>) -> Result<Option<Value>, Unsupported> {
    Ok(Some(Value::Number(value.into())))
}

impl Serializer for Scalar {
    type Ok = Option<Value>;
    type Error = Unsupported;
    type SerializeSeq = Skipped;
    type SerializeTuple = Skipped;
    type SerializeTupleStruct = Skipped;
    type SerializeTupleVariant = Skipped;
    type SerializeMap = Skipped;
    type SerializeStruct = Skipped;
    type SerializeStructVariant = Skipped;

    fn serialize_bool(self, value: bool) -> Result<Self::Ok, Unsupported> {
        Ok(Some(Value::Bool(value)))
    }

    fn serialize_i8(self, value: i8) -> Result<Self::Ok, Unsupported> {
        number(value)
    }

    fn serialize_i16(self, value: i16) -> Result<Self::Ok, Unsupported> {
        number(value)
    }

    fn serialize_i32(self, value: i32) -> Result<Self::Ok, Unsupported> {
        number(value)
    }

    fn serialize_i64(self, value: i64) -> Result<Self::Ok, Unsupported> {
        number(value)
    }

    fn serialize_u8(self, value: u8) -> Result<Self::Ok, Unsupported> {
        number(value)
    }

    fn serialize_u16(self, value: u16) -> Result<Self::Ok, Unsupported> {
        number(value)
    }

    fn serialize_u32(self, value: u32) -> Result<Self::Ok, Unsupported> {
        number(value)
    }

    fn serialize_u64(self, value: u64) -> Result<Self::Ok, Unsupported> {
        number(value)
    }

    fn serialize_f32(self, value: f32) -> Result<Self::Ok, Unsupported> {
        self.serialize_f64(f64::from(value))
    }

    fn serialize_f64(self, value: f64) -> Result<Self::Ok, Unsupported> {
        Ok(Number::from_f64(value).map(Value::Number))
    }

    fn serialize_char(self, value: char) -> Result<Self::Ok, Unsupported> {
        Ok(Some(Value::String(value.to_string())))
    }

    fn serialize_str(self, value: &str) -> Result<Self::Ok, Unsupported> {
        Ok(Some(Value::String(value.to_owned())))
    }

    fn serialize_bytes(self, _value: &[u8]) -> Result<Self::Ok, Unsupported> {
        Ok(None)
    }

    fn serialize_none(self) -> Result<Self::Ok, Unsupported> {
        Ok(Some(Value::Null))
    }

    fn serialize_some<T: ?Sized + Serialize>(self, value: &T) -> Result<Self::Ok, Unsupported> {
        value.serialize(self)
    }

    fn serialize_unit(self) -> Result<Self::Ok, Unsupported> {
        Ok(Some(Value::Null))
    }

    fn serialize_unit_struct(self, _name: &'static str) -> Result<Self::Ok, Unsupported> {
        Ok(Some(Value::Null))
    }

    fn serialize_unit_variant(
        self,
        _name: &'static str,
        _index: u32,
        variant: &'static str,
    ) -> Result<Self::Ok, Unsupported> {
        Ok(Some(Value::String(variant.to_owned())))
    }

    fn serialize_newtype_struct<T: ?Sized + Serialize>(
        self,
        _name: &'static str,
        value: &T,
    ) -> Result<Self::Ok, Unsupported> {
        value.serialize(self)
    }

    fn serialize_newtype_variant<T: ?Sized + Serialize>(
        self,
        _name: &'static str,
        _index: u32,
        _variant: &'static str,
        _value: &T,
    ) -> Result<Self::Ok, Unsupported> {
        Ok(None)
    }

    fn serialize_seq(self, _len: Option<usize>) -> Result<Skipped, Unsupported> {
        Ok(Skipped)
    }

    fn serialize_tuple(self, _len: usize) -> Result<Skipped, Unsupported> {
        Ok(Skipped)
    }

    fn serialize_tuple_struct(
        self,
        _name: &'static str,
        _len: usize,
    ) -> Result<Skipped, Unsupported> {
        Ok(Skipped)
    }

    fn serialize_tuple_variant(
        self,
        _name: &'static str,
        _index: u32,
        _variant: &'static str,
        _len: usize,
    ) -> Result<Skipped, Unsupported> {
        Ok(Skipped)
    }

    fn serialize_map(self, _len: Option<usize>) -> Result<Skipped, Unsupported> {
        Ok(Skipped)
    }

    fn serialize_struct(self, _name: &'static str, _len: usize) -> Result<Skipped, Unsupported> {
        Ok(Skipped)
    }

    fn serialize_struct_variant(
        self,
        _name: &'static str,
        _index: u32,
        _variant: &'static str,
        _len: usize,
    ) -> Result<Skipped, Unsupported> {
        Ok(Skipped)
    }
}
