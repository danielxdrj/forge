const variants = {
  primary:
    "bg-forge-blue text-white hover:bg-forge-blue-bright disabled:hover:bg-forge-blue",
  ghost:
    "border border-forge-line bg-transparent text-forge-text hover:bg-forge-raised",
};

export default function Button({
  variant = "primary",
  className = "",
  type = "button",
  children,
  ...props
}) {
  return (
    <button
      type={type}
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-medium ${variants[variant]} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
