export default function PageHeader({
  title,
  description,
  actions,
  badge,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  badge?: React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between mb-8">
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold text-gray-900 tracking-tight">{title}</h1>
          {badge}
        </div>
        {description && (
          <p className="mt-1.5 text-sm text-gray-500 leading-relaxed">{description}</p>
        )}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
