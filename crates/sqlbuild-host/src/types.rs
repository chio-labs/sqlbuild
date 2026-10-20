//! What every executor result enum provides.

/// A Rust mirror of one Python string enum of executor results.
pub trait ResultEnum: Copy + 'static {
    /// Every member, in Python definition order.
    const ALL: &'static [Self];

    /// The member's Python value.
    fn value(self) -> &'static str;

    /// The member whose Python value is `value`.
    fn from_value(value: &str) -> Option<Self> {
        Self::ALL
            .iter()
            .copied()
            .find(|member| member.value() == value)
    }
}
