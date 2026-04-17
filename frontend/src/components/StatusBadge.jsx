export default function StatusBadge({ children, tone = "primary" }) {
  const classes = {
    primary:
      "border border-primary/20 bg-primary/15 text-[#005b52] dark:border-primary/35 dark:bg-primary/20 dark:text-[#8ff7ea]",
    success:
      "border border-[#2E7D32]/15 bg-[#E5F5E0] text-[#1B5E20] dark:border-[#6adf8a]/25 dark:bg-[#123323] dark:text-[#86efac]",
    warning:
      "border border-[#E65100]/15 bg-[#FFF3E0] text-[#B45309] dark:border-[#f59e0b]/25 dark:bg-[#3a2410] dark:text-[#fbbf24]",
    neutral:
      "border border-outline-variant/20 bg-surface-container-high text-on-surface dark:border-outline-variant/30 dark:bg-surface-container-highest dark:text-[#e6eefc]",
  };

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-bold uppercase tracking-wider ${classes[tone] || classes.primary}`}
    >
      {children}
    </span>
  );
}
