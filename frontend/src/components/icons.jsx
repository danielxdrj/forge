function Icon({ children, className = "size-5" }) {
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {children}
    </svg>
  );
}

export function IconMark({ className }) {
  return (
    <Icon className={className}>
      <path d="M12 3l2.2 6.2L20 12l-5.8 2.8L12 21l-2.2-6.2L4 12l5.8-2.8L12 3z" />
    </Icon>
  );
}

export function IconInvestigation({ className }) {
  return (
    <Icon className={className}>
      <circle cx="11" cy="11" r="6" />
      <path d="M20 20l-3.2-3.2" />
      <path d="M11 8v3l2 1.5" />
    </Icon>
  );
}

export function IconAutomation({ className }) {
  return (
    <Icon className={className}>
      <path d="M12 3v3M12 18v3M3 12h3M18 12h3" />
      <circle cx="12" cy="12" r="4" />
    </Icon>
  );
}

export function IconLog({ className }) {
  return (
    <Icon className={className}>
      <path d="M6 4h9l3 3v13H6z" />
      <path d="M15 4v3h3M8 12h8M8 16h5" />
    </Icon>
  );
}

export function IconConnection({ className }) {
  return (
    <Icon className={className}>
      <path d="M8 8l-3 3 3 3M16 8l3 3-3 3M10 16l4-8" />
    </Icon>
  );
}

export function IconSettings({ className }) {
  return (
    <Icon className={className}>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 3v2.2M12 18.8V21M3 12h2.2M18.8 12H21M5.6 5.6l1.6 1.6M16.8 16.8l1.6 1.6M18.4 5.6l-1.6 1.6M7.2 16.8l-1.6 1.6" />
    </Icon>
  );
}

export function IconSearch({ className }) {
  return (
    <Icon className={className}>
      <circle cx="11" cy="11" r="6" />
      <path d="M20 20l-3.2-3.2" />
    </Icon>
  );
}

export function IconPlus({ className }) {
  return (
    <Icon className={className}>
      <path d="M12 5v14M5 12h14" />
    </Icon>
  );
}

export function IconPanel({ className }) {
  return (
    <Icon className={className}>
      <rect x="4" y="5" width="16" height="14" rx="2" />
      <path d="M10 5v14" />
    </Icon>
  );
}

export function IconClose({ className }) {
  return (
    <Icon className={className}>
      <path d="M6 6l12 12M18 6L6 18" />
    </Icon>
  );
}

export function IconUser({ className }) {
  return (
    <Icon className={className}>
      <circle cx="12" cy="8" r="3" />
      <path d="M5 19c1.4-3 3.6-4.5 7-4.5S17.6 16 19 19" />
    </Icon>
  );
}
