export default function Tabs({ label, tabs, active, onChange }) {
  return (
    <div role="tablist" aria-label={label} className="flex gap-1 overflow-x-auto border-b border-forge-line">
      {tabs.map((tab) => {
        const selected = active === tab.id;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            id={`${tab.id}-tab`}
            aria-selected={selected}
            aria-controls={`${tab.id}-panel`}
            className={`shrink-0 border-b-2 px-3 py-2 text-sm ${
              selected
                ? "border-forge-blue text-forge-text"
                : "border-transparent text-forge-muted hover:text-forge-text"
            }`}
            onClick={() => onChange(tab.id)}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
