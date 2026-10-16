//! `ReadyQueue` for first-in-first-out and smallest-first queues.

use std::cmp::Reverse;
use std::collections::{BinaryHeap, VecDeque};

use crate::graph_walk::types::ReadyQueue;

impl<K> ReadyQueue<K> for VecDeque<K> {
    fn offer(&mut self, key: K) {
        self.push_back(key);
    }

    fn take(&mut self) -> Option<K> {
        self.pop_front()
    }
}

impl<K: Ord> ReadyQueue<K> for BinaryHeap<Reverse<K>> {
    fn offer(&mut self, key: K) {
        self.push(Reverse(key));
    }

    fn take(&mut self) -> Option<K> {
        self.pop().map(|Reverse(key)| key)
    }
}
