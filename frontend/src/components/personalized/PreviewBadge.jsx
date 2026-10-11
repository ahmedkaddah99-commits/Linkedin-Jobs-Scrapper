export default function PreviewBadge({ className = "" }) {
  return (
    <span className={["preview-badge", className].join(" ")}>
      <span className="material-symbols-outlined text-[15px]">science</span>
      Preview data
    </span>
  );
}

