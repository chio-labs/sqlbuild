//! `directed_path_nodes`: the nodes on directed paths from one node to another.

use crate::graph_walk::main::breadth_first_reach::breadth_first_reach;
use crate::graph_walk::types::NodeSet;

/// Record in `path` every node on a downstream path from `start` to `end`, both included; false when `end` is not downstream of `start`.
pub fn directed_path_nodes<K, S, I, J, D, U>(
    (start, end): (K, K),
    (downstream, mut upstream): (D, U),
    (reachable, path): (&mut S, &mut S),
) -> Result<bool, S::Error>
where
    K: Clone,
    S: NodeSet<K>,
    I: IntoIterator<Item = K>,
    J: IntoIterator<Item = K>,
    D: FnMut(&K) -> Result<I, S::Error>,
    U: FnMut(&K) -> Result<J, S::Error>,
{
    breadth_first_reach([start.clone()], None, reachable, downstream)?;
    if !reachable.holds(&end)? {
        return Ok(false);
    }
    reachable.insert_new(&start)?;
    let mut pending: Vec<K> = vec![end];
    while let Some(current) = pending.pop() {
        if !path.insert_new(&current)? {
            continue;
        }
        for parent in upstream(&current)? {
            if reachable.holds(&parent)? {
                pending.push(parent);
            }
        }
    }
    Ok(true)
}
