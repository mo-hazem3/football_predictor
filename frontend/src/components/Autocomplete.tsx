import { useId, useState, type KeyboardEvent, type ReactNode } from "react";

import { useDebounced } from "../lib/useDebounced";

interface Props<T> {
  label: string;
  placeholder: string;
  compact?: boolean;
  autoFocus?: boolean;
  /** Query hook for a (debounced) search string; must be disabled itself for strings that are too short. */
  useResults: (q: string) => { data: T[] | undefined; isFetching: boolean; error: unknown };
  getKey: (item: T) => string | number;
  renderItem: (item: T) => ReactNode;
  onSelect: (item: T) => void;
  emptyText: string;
}

/** ARIA combobox with a listbox popup: type to search, Up/Down to move, Enter to choose, Escape to close. */
export function Autocomplete<T>({ label, placeholder, compact, autoFocus, useResults, getKey, renderItem, onSelect, emptyText }: Props<T>) {
  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const listId = useId();
  const debounced = useDebounced(text.trim(), 200);
  const { data, isFetching, error } = useResults(debounced);

  const long = text.trim().length >= 2;
  const items = long ? (data ?? []) : [];
  const showPopup = open && long;

  function choose(item: T) {
    setOpen(false);
    setText("");
    onSelect(item);
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActive((i) => Math.min(i + 1, Math.max(items.length - 1, 0)));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && showPopup && items[active]) {
      e.preventDefault();
      choose(items[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <div className={`combobox${compact ? " compact" : ""}`}>
      <label htmlFor={`${listId}-input`} className={compact ? "sr-only" : undefined}>
        {label}
      </label>
      <input
        id={`${listId}-input`}
        type="search"
        role="combobox"
        aria-expanded={showPopup}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={showPopup && items[active] ? `${listId}-opt-${active}` : undefined}
        autoComplete="off"
        autoFocus={autoFocus}
        placeholder={placeholder}
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setOpen(true);
          setActive(0);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        onKeyDown={onKeyDown}
      />
      {showPopup && (
        <ul id={listId} role="listbox" className="listbox" aria-label={`${label} results`}>
          {items.map((item, i) => (
            <li
              key={getKey(item)}
              id={`${listId}-opt-${i}`}
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => choose(item)}
              onMouseEnter={() => setActive(i)}
            >
              {renderItem(item)}
            </li>
          ))}
          {!items.length && (
            <li role="option" aria-selected={false} aria-disabled className="empty">
              {error ? "Search failed" : isFetching ? "Searching…" : emptyText}
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
