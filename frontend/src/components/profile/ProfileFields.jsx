import { useState } from "react";

export function Field({ label, children, wide }) {
  return <label className={`profile-edit-field${wide ? " profile-edit-field--wide" : ""}`}><span>{label}</span>{children}</label>;
}

export function TextField({ label, value, onChange, type = "text", wide, ...props }) {
  return <Field label={label} wide={wide}><input {...props} type={type} value={value ?? ""} onChange={event => onChange(event.target.value)} /></Field>;
}

export function Chips({ label, values = [], onChange }) {
  const [text, setText] = useState("");
  function add() {
    const next = text.trim();
    if (next && !values.some(value => value.toLowerCase() === next.toLowerCase())) onChange([...values, next]);
    setText("");
  }
  return <div className="profile-chip-editor"><label htmlFor={`profile-chip-${label}`}>{label}</label><div className="profile-chip-values">{values.map((value, index) => <span key={`${index}-${value}`}>{value}<button aria-label={`Remove ${value}`} onClick={() => onChange(values.filter((_, i) => i !== index))} type="button">×</button></span>)}</div><div className="profile-chip-add"><input id={`profile-chip-${label}`} placeholder={`Add ${label.toLowerCase()}`} value={text} onChange={e => setText(e.target.value)} onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); add(); } }} /><button onClick={add} disabled={!text.trim()} type="button">Add</button></div></div>;
}

export function BulletEditor({ values = [], onChange }) {
  return <div className="profile-bullet-editor"><span>Job description</span>{values.map((value, index) => <div key={index}><textarea aria-label={`Bullet point ${index + 1}`} rows="2" value={value} onChange={e => onChange(values.map((old, i) => i === index ? e.target.value : old))} /><button aria-label={`Remove bullet point ${index + 1}`} onClick={() => onChange(values.filter((_, i) => i !== index))} type="button">×</button></div>)}<button className="profile-edit-add" onClick={() => onChange([...values, ""])} type="button">+ Bullet point</button></div>;
}

export function Choices({ label, values = [], options, onChange }) {
  return <fieldset className="profile-choice-field"><legend>{label}</legend>{options.map(([value, text]) => <button aria-pressed={values.includes(value)} key={value} onClick={() => onChange(values.includes(value) ? values.filter(item => item !== value) : [...values, value])} type="button">{text}</button>)}</fieldset>;
}
