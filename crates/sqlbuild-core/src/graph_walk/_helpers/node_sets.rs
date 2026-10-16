//! `NodeSet` for the standard sets.

use std::collections::{BTreeSet, HashSet};
use std::convert::Infallible;
use std::hash::Hash;

use crate::graph_walk::types::NodeSet;

impl<K: Eq + Hash + Clone> NodeSet<K> for HashSet<K> {
    type Error = Infallible;

    fn insert_new(&mut self, key: &K) -> Result<bool, Infallible> {
        Ok(!self.contains(key) && self.insert(key.clone()))
    }

    fn holds(&self, key: &K) -> Result<bool, Infallible> {
        Ok(self.contains(key))
    }
}

impl<K: Ord + Clone> NodeSet<K> for BTreeSet<K> {
    type Error = Infallible;

    fn insert_new(&mut self, key: &K) -> Result<bool, Infallible> {
        Ok(!self.contains(key) && self.insert(key.clone()))
    }

    fn holds(&self, key: &K) -> Result<bool, Infallible> {
        Ok(self.contains(key))
    }
}
