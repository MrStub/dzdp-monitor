import * as React from "react";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

const Select = React.forwardRef<
  HTMLSelectElement,
  React.ComponentProps<"select">
>(
  (
    { className, children, disabled, onChange, value, defaultValue, name, required, ...props },
    ref,
  ) => {
    const [open, setOpen] = React.useState(false);
    const [focusedIndex, setFocusedIndex] = React.useState(-1);
    const containerRef = React.useRef<HTMLDivElement>(null);
    const selectRef = React.useRef<HTMLSelectElement | null>(null);

    React.useImperativeHandle(ref, () => selectRef.current as HTMLSelectElement);

    const options = React.useMemo(
      () =>
        React.Children.toArray(children).flatMap((child) => {
          if (!React.isValidElement<React.ComponentProps<"option">>(child)) {
            return [];
          }

          const optionValue = child.props.value;
          return [
            {
              value: optionValue == null ? "" : String(optionValue),
              label: React.Children.toArray(child.props.children).join(""),
              disabled: Boolean(child.props.disabled),
            },
          ];
        }),
      [children],
    );

    const currentValue = value == null ? String(defaultValue ?? "") : String(value);
    const selectedOption = options.find((option) => option.value === currentValue) ?? options[0];

    const enabledOptions = options.filter((option) => !option.disabled);

    React.useEffect(() => {
      if (!open) {
        return;
      }

      const handlePointerDown = (event: MouseEvent | TouchEvent) => {
        if (!containerRef.current?.contains(event.target as Node)) {
          setOpen(false);
          setFocusedIndex(-1);
        }
      };

      document.addEventListener("mousedown", handlePointerDown);
      document.addEventListener("touchstart", handlePointerDown);
      return () => {
        document.removeEventListener("mousedown", handlePointerDown);
        document.removeEventListener("touchstart", handlePointerDown);
      };
    }, [open]);

    React.useEffect(() => {
      if (!open) {
        setFocusedIndex(-1);
        return;
      }

      const activeIndex = enabledOptions.findIndex((option) => option.value === selectedOption?.value);
      setFocusedIndex(activeIndex >= 0 ? activeIndex : 0);
    }, [enabledOptions, open, selectedOption?.value]);

    const emitChange = React.useCallback(
      (nextValue: string) => {
        if (!onChange || nextValue === currentValue) {
          return;
        }

        onChange({ target: { value: nextValue } } as React.ChangeEvent<HTMLSelectElement>);
      },
      [currentValue, onChange],
    );

    const handleSelect = React.useCallback(
      (nextValue: string) => {
        emitChange(nextValue);
        setOpen(false);
      },
      [emitChange],
    );

    const handleKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>) => {
      if (disabled || enabledOptions.length === 0) {
        return;
      }

      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        if (!open) {
          setOpen(true);
          return;
        }

        setFocusedIndex((current) => {
          const start = current >= 0 ? current : 0;
          const delta = event.key === "ArrowDown" ? 1 : -1;
          return (start + delta + enabledOptions.length) % enabledOptions.length;
        });
        return;
      }

      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        if (open && focusedIndex >= 0) {
          handleSelect(enabledOptions[focusedIndex].value);
          return;
        }
        setOpen((current) => !current);
        return;
      }

      if (event.key === "Escape") {
        setOpen(false);
      }
    };

    return (
      <div ref={containerRef} className="relative">
        <select
          ref={selectRef}
          className="sr-only"
          disabled={disabled}
          name={name}
          onChange={onChange}
          required={required}
          tabIndex={-1}
          value={currentValue}
          {...props}
        >
          {children}
        </select>
        <button
          type="button"
          disabled={disabled}
          aria-expanded={open}
          aria-haspopup="listbox"
          className={cn(
            "flex min-h-[2.75rem] w-full items-center rounded-xl border border-input/80 bg-white px-4 py-2.5 pr-11 text-left text-[15px] leading-6 text-foreground shadow-sm transition-colors focus-visible:border-primary/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/25 disabled:cursor-not-allowed disabled:bg-muted/40 disabled:opacity-70 sm:min-h-[2.875rem]",
            className,
          )}
          onClick={() => setOpen((current) => !current)}
          onKeyDown={handleKeyDown}
        >
          <span className="block flex-1 truncate">{selectedOption?.label ?? ""}</span>
          <ChevronDown
            className={cn(
              "pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/90 transition-transform",
              open ? "rotate-180" : "",
            )}
          />
        </button>
        {open ? (
          <div className="absolute left-0 right-0 top-[calc(100%+0.5rem)] z-30 rounded-2xl border border-border/70 bg-white/98 p-1.5 shadow-[0_18px_40px_rgba(15,23,42,0.14)] backdrop-blur">
            <div className="max-h-72 overflow-y-auto overscroll-contain rounded-[1rem] p-0.5">
              {options.map((option) => {
                const isSelected = option.value === selectedOption?.value;
                const isFocused =
                  focusedIndex >= 0 && enabledOptions[focusedIndex]?.value === option.value;

                return (
                  <button
                    key={option.value}
                    type="button"
                    role="option"
                    aria-selected={isSelected}
                    disabled={option.disabled}
                    className={cn(
                      "flex min-h-[2.625rem] w-full items-center justify-between rounded-[0.9rem] px-3.5 py-2.5 text-left text-[15px] leading-6 transition-colors",
                      option.disabled
                        ? "cursor-not-allowed text-muted-foreground/60"
                        : "text-foreground hover:bg-secondary/70",
                      isSelected ? "bg-primary/10 text-foreground" : "",
                      isFocused ? "bg-secondary/80" : "",
                    )}
                    onClick={() => handleSelect(option.value)}
                    onMouseEnter={() => {
                      const index = enabledOptions.findIndex(
                        (enabledOption) => enabledOption.value === option.value,
                      );
                      if (index >= 0) {
                        setFocusedIndex(index);
                      }
                    }}
                  >
                    <span className="pr-3">{option.label}</span>
                    {isSelected ? <Check className="h-4 w-4 text-primary" /> : null}
                  </button>
                );
              })}
            </div>
          </div>
        ) : null}
      </div>
    );
  },
);
Select.displayName = "Select";

export { Select };
