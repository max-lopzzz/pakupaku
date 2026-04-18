import { useState } from "react";
import { CONDITION_NOTES } from "../constants/conditionNotes";
import "./HealthNotesCard.css";

interface HealthNotesCardProps {
  conditions: string[];
}

export default function HealthNotesCard({ conditions }: HealthNotesCardProps) {
  const known = conditions.filter(c => CONDITION_NOTES[c]);
  if (known.length === 0) return null;

  return (
    <div className="hnc-root">
      <h2 className="hnc-title">Health Notes</h2>
      {known.map(key => (
        <ConditionRow key={key} conditionKey={key} />
      ))}
    </div>
  );
}

function ConditionRow({ conditionKey }: { conditionKey: string }) {
  const [open, setOpen] = useState(true);
  const note = CONDITION_NOTES[conditionKey];
  if (!note) return null;

  return (
    <div className="hnc-row">
      <button
        className="hnc-row-header"
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
      >
        <span className="hnc-row-label">{note.label}</span>
        <span className="hnc-chevron">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <ul className="hnc-notes">
          {note.dashboardNotes.map((bullet, i) => (
            <li key={i}>{bullet}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
