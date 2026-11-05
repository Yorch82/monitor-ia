/** Tarjeta genérica de panel (header + contenido). */

import type { ReactNode } from "react";

export function Card({
  title,
  icon,
  actions,
  children,
  className = "",
  bodyClassName = "",
}: {
  title?: ReactNode;
  icon?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={`card flex flex-col ${className}`}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-white/[0.05] px-4 py-3">
          <div className="flex items-center gap-2 text-slate-300">
            {icon && <span className="text-accent-cyan">{icon}</span>}
            {title && <h2 className="card-title">{title}</h2>}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={`flex-1 p-4 ${bodyClassName}`}>{children}</div>
    </section>
  );
}
