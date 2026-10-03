import { useEffect, useState } from "react";
import { useApp } from "../store.jsx";

export function Badge({ tone, children, title }) {
  return (
    <span className={`badge ${tone || ""}`} title={title}>
      {children}
    </span>
  );
}

export function Card({ label, value, hint, tone, onClick, children }) {
  return (
    <div className={`card ${tone || ""} ${onClick ? "clickable" : ""}`} onClick={onClick} role={onClick ? "button" : undefined}>
      <div className="card-label">{label}</div>
      {value !== undefined && <b>{value}</b>}
      {hint && <div className="muted small">{hint}</div>}
      {children}
    </div>
  );
}

export function Section({ title, aside, children, className }) {
  return (
    <section className={`section ${className || ""}`}>
      {(title || aside) && (
        <div className="section-head">
          {title && <h2>{title}</h2>}
          {aside && <div className="section-aside">{aside}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

export function Empty({ children, action }) {
  const { t } = useApp();
  return (
    <div className="empty">
      <p className="muted">{children || t("Nothing here yet.")}</p>
      {action}
    </div>
  );
}

export function Banner({ tone, children, onClose }) {
  return (
    <div className={`banner ${tone || ""}`}>
      <div>{children}</div>
      {onClose && (
        <button className="link" onClick={onClose} aria-label="close">
          ×
        </button>
      )}
    </div>
  );
}

export function RelativeTime({ value }) {
  const { t } = useApp();
  if (!value) return <span className="muted">—</span>;
  const date = new Date(value);
  const diff = Math.max(0, Date.now() - date.getTime());
  const minutes = Math.floor(diff / 60000);
  let text;
  if (minutes < 1) text = t("just now");
  else if (minutes < 60) text = t("{n} min ago", { n: minutes });
  else if (minutes < 60 * 24) text = t("{n} h ago", { n: Math.floor(minutes / 60) });
  else text = t("{n} d ago", { n: Math.floor(minutes / (60 * 24)) });
  return (
    <time dateTime={value} title={date.toLocaleString()} className="reltime">
      {text}
    </time>
  );
}

export function Duration({ since }) {
  const { t } = useApp();
  if (!since) return null;
  const diff = Math.max(0, Date.now() - new Date(since).getTime());
  const minutes = Math.floor(diff / 60000);
  const text =
    minutes < 60
      ? `${minutes} min`
      : minutes < 60 * 24
        ? `${Math.floor(minutes / 60)} h`
        : `${Math.floor(minutes / (60 * 24))} d`;
  return <span>{t("Open for {time}", { time: text })}</span>;
}

export function Confirm({ open, title, body, confirmLabel, tone, onConfirm, onCancel }) {
  const { t } = useApp();
  if (!open) return null;
  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal" onClick={(event) => event.stopPropagation()}>
        <h3>{title || t("Are you sure?")}</h3>
        {body && <p className="muted">{body}</p>}
        <div className="actions right">
          <button className="btn ghost" onClick={onCancel}>
            {t("Cancel")}
          </button>
          <button className={`btn ${tone || "danger"}`} onClick={onConfirm}>
            {confirmLabel || t("Confirm")}
          </button>
        </div>
      </div>
    </div>
  );
}

export function useConfirm() {
  const [state, setState] = useState(null);
  const ask = (options) =>
    new Promise((resolve) => {
      setState({ ...options, resolve });
    });
  const element = (
    <Confirm
      open={Boolean(state)}
      title={state?.title}
      body={state?.body}
      confirmLabel={state?.confirmLabel}
      tone={state?.tone}
      onConfirm={() => {
        state?.resolve(true);
        setState(null);
      }}
      onCancel={() => {
        state?.resolve(false);
        setState(null);
      }}
    />
  );
  return [ask, element];
}

export function Drawer({ open, title, onClose, children, wide }) {
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event) => event.key === "Escape" && onClose?.();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside className={`drawer ${wide ? "wide" : ""}`} onClick={(event) => event.stopPropagation()}>
        <div className="drawer-head">
          <h2>{title}</h2>
          <button className="link" onClick={onClose} aria-label="close">
            ×
          </button>
        </div>
        <div className="drawer-body">{children}</div>
      </aside>
    </div>
  );
}

export function Toasts() {
  const { toasts, dismissToast } = useApp();
  if (!toasts.length) return null;
  return (
    <div className="toasts">
      {toasts.map((item) => (
        <div
          key={item.id}
          className={`toast ${item.tone || ""} ${item.onClick ? "clickable" : ""}`}
          onClick={() => {
            item.onClick?.();
            dismissToast(item.id);
          }}
        >
          {item.count > 1 && <span className="toast-count">{item.count}</span>}
          <span>{item.message}</span>
        </div>
      ))}
    </div>
  );
}

export function Filters({ children }) {
  return <div className="filters">{children}</div>;
}

export function Select({ value, onChange, options, placeholder, ...rest }) {
  return (
    <select value={value ?? ""} onChange={(event) => onChange(event.target.value)} {...rest}>
      {placeholder !== undefined && <option value="">{placeholder}</option>}
      {options.map((option) => {
        const [val, label] = Array.isArray(option) ? option : [option, option];
        return (
          <option key={val} value={val}>
            {label}
          </option>
        );
      })}
    </select>
  );
}

// ---------------------------------------------------------------- charts (SVG)

export function Sparkline({ points, height = 36, width = 160, tone }) {
  const values = points.map((item) => (typeof item === "number" ? item : item.count ?? 0));
  const max = Math.max(1, ...values);
  const step = values.length > 1 ? width / (values.length - 1) : width;
  const path = values
    .map((value, index) => `${index === 0 ? "M" : "L"}${(index * step).toFixed(1)},${(height - (value / max) * (height - 4) - 2).toFixed(1)}`)
    .join(" ");
  return (
    <svg className={`spark ${tone || ""}`} viewBox={`0 0 ${width} ${height}`} width="100%" height={height} preserveAspectRatio="none">
      <path d={path} fill="none" strokeWidth="2" />
      {values.map((value, index) =>
        value ? <circle key={index} cx={(index * step).toFixed(1)} cy={(height - (value / max) * (height - 4) - 2).toFixed(1)} r="2" /> : null
      )}
    </svg>
  );
}

export function StackedBars({ rows, keys, labels, height = 120 }) {
  const totals = rows.map((row) => keys.reduce((sum, key) => sum + (row[key] || 0), 0));
  const max = Math.max(1, ...totals);
  return (
    <div className="bars" style={{ height }}>
      {rows.map((row, index) => (
        <div key={index} className="bar-col" title={`${row.hour || row.label}: ${totals[index]}`}>
          <div className="bar-stack">
            {keys.map((key) => (
              <div key={key} className={`bar-seg ${key}`} style={{ height: `${((row[key] || 0) / max) * 100}%` }} />
            ))}
          </div>
          {(index % 4 === 0 || index === rows.length - 1) && <div className="bar-label">{row.hour || row.label}</div>}
        </div>
      ))}
      {labels && (
        <div className="legend">
          {keys.map((key) => (
            <span key={key}>
              <i className={`swatch ${key}`} /> {labels[key] || key}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export function HBars({ rows, labelKey, valueKey = "count", onClick, tone }) {
  const max = Math.max(1, ...rows.map((row) => row[valueKey] || 0));
  if (!rows.length) return <Empty />;
  return (
    <div className="hbars">
      {rows.map((row) => (
        <div key={row[labelKey]} className={`hbar ${onClick ? "clickable" : ""}`} onClick={onClick ? () => onClick(row) : undefined}>
          <span className="hbar-label" title={row[labelKey]}>
            {row[labelKey]}
          </span>
          <span className="hbar-track">
            <span className={`hbar-fill ${tone || ""}`} style={{ width: `${((row[valueKey] || 0) / max) * 100}%` }} />
          </span>
          <span className="hbar-value">{row[valueKey]}</span>
        </div>
      ))}
    </div>
  );
}

export function Gauge({ value, size = 120, label }) {
  const clamped = Math.max(0, Math.min(100, value || 0));
  const radius = (size - 12) / 2;
  const circumference = 2 * Math.PI * radius;
  const tone = clamped >= 80 ? "ok" : clamped >= 50 ? "warn" : "danger";
  return (
    <div className={`gauge ${tone}`} style={{ width: size, height: size }}>
      <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size}>
        <circle cx={size / 2} cy={size / 2} r={radius} className="gauge-track" strokeWidth="10" fill="none" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          className="gauge-fill"
          strokeWidth="10"
          fill="none"
          strokeDasharray={`${(clamped / 100) * circumference} ${circumference}`}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <div className="gauge-value">
        <b>{Math.round(clamped)}</b>
        {label && <span className="muted small">{label}</span>}
      </div>
    </div>
  );
}

export function Progress({ pct, alert = 80 }) {
  const clamped = Math.max(0, Math.min(100, pct || 0));
  const tone = clamped >= 100 ? "danger" : clamped >= alert ? "warn" : "ok";
  return (
    <div className="progress" title={`${Math.round(pct || 0)}%`}>
      <div className={`progress-fill ${tone}`} style={{ width: `${clamped}%` }} />
    </div>
  );
}

export function riskTone(risk) {
  return risk || "none";
}

export function Labels({ items, max = 6 }) {
  if (!items?.length) return <span className="muted">—</span>;
  const shown = items.slice(0, max);
  return (
    <span className="labels">
      {shown.map((item) => (
        <code key={item}>{item}</code>
      ))}
      {items.length > max && <span className="muted">+{items.length - max}</span>}
    </span>
  );
}
