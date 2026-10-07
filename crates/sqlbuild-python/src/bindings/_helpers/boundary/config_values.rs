//! Loaded configuration values as the Python objects PyYAML and `tomllib` build.

use pyo3::IntoPyObjectExt;
use pyo3::prelude::{Bound, IntoPyObject, Py, PyAny, PyAnyMethods, PyModule, PyResult, Python};
use pyo3::types::{IntoPyDict, PyDict, PyDictMethods, PyList, PyListMethods};
use sqlbuild_config::models::{ConfigDate, ConfigDateTime, ConfigTime, ConfigValue};

type PyObject = Py<PyAny>;

/// Decimal digits per `int(str)` call, well below Python's default 4300-digit limit.
const BIG_INTEGER_CHUNK_DIGITS: usize = 1000;

fn object<'py, T: IntoPyObject<'py>>(py: Python<'py>, value: T) -> PyResult<PyObject> {
    value.into_py_any(py)
}

fn date(datetime: &Bound<'_, PyModule>, value: ConfigDate) -> PyResult<PyObject> {
    Ok(datetime
        .getattr("date")?
        .call1((value.year, value.month, value.day))?
        .unbind())
}

fn time(datetime: &Bound<'_, PyModule>, value: ConfigTime) -> PyResult<PyObject> {
    Ok(datetime
        .getattr("time")?
        .call1((value.hour, value.minute, value.second, value.microsecond))?
        .unbind())
}

fn date_time(datetime: &Bound<'_, PyModule>, value: ConfigDateTime) -> PyResult<PyObject> {
    let tzinfo: Option<Bound<'_, PyAny>> = match value.utc_offset_seconds {
        Some(seconds) => {
            let delta = datetime.getattr("timedelta")?.call(
                (),
                Some(&[("seconds", seconds)].into_py_dict(datetime.py())?),
            )?;
            Some(datetime.getattr("timezone")?.call1((delta,))?)
        }
        None => None,
    };
    let (date, time) = (value.date, value.time);
    Ok(datetime
        .getattr("datetime")?
        .call1((
            date.year,
            date.month,
            date.day,
            time.hour,
            time.minute,
            time.second,
            time.microsecond,
            tzinfo,
        ))?
        .unbind())
}

/// Python's `int` of a decimal text of any length, built from chunks below the conversion limit.
fn big_integer(py: Python<'_>, text: &str) -> PyResult<PyObject> {
    let (negative, digits) = match text.strip_prefix('-') {
        Some(digits) => (true, digits),
        None => (false, text),
    };
    let int = py.import("builtins")?.getattr("int")?;
    let mut value: Bound<'_, PyAny> = int.call1((0,))?;
    for chunk in digits.as_bytes().chunks(BIG_INTEGER_CHUNK_DIGITS) {
        let chunk_text = std::str::from_utf8(chunk)
            .map_err(|error| pyo3::exceptions::PyValueError::new_err(error.to_string()))?;
        let scale = int.call1((10,))?.pow(chunk.len(), py.None())?;
        value = value.mul(scale)?.add(int.call1((chunk_text,))?)?;
    }
    if negative {
        value = value.neg()?;
    }
    Ok(value.unbind())
}

/// Build the Python object for one loaded value; mapping entries keep their document order.
pub(crate) fn config_value_to_python(py: Python<'_>, value: ConfigValue) -> PyResult<PyObject> {
    match value {
        ConfigValue::Null => Ok(py.None()),
        ConfigValue::Bool(flag) => object(py, flag),
        ConfigValue::Integer(number) => object(py, number),
        ConfigValue::BigInteger(text) => big_integer(py, &text),
        ConfigValue::Float(number) => object(py, number),
        ConfigValue::String(text) => object(py, text),
        ConfigValue::Date(value) => date(&py.import("datetime")?, value),
        ConfigValue::DateTime(value) => date_time(&py.import("datetime")?, value),
        ConfigValue::Time(value) => time(&py.import("datetime")?, value),
        ConfigValue::List(items) => {
            let list = PyList::empty(py);
            for item in items {
                list.append(config_value_to_python(py, item)?)?;
            }
            Ok(list.unbind().into_any())
        }
        ConfigValue::Map(entries) => {
            let mapping = PyDict::new(py);
            for (key, item) in entries {
                mapping.set_item(
                    config_value_to_python(py, key)?,
                    config_value_to_python(py, item)?,
                )?;
            }
            Ok(mapping.unbind().into_any())
        }
    }
}
