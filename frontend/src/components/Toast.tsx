"use client";

import { useEffect, useState, useCallback, createContext, useContext } from "react";
import { cn } from "@/lib/utils";

export type ToastVariant = "error" | "success" | "info";

export interface ToastMessage {
  id: string;
  message: string;
  variant: ToastVariant;
}

interface ToastContextValue {
  showToast: (message: string, variant?: ToastVariant) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return ctx;
}

const TOAST_DURATION_MS = 5000;

function ToastItem({ toast, onDismiss }: { toast: ToastMessage; onDismiss: (id: string) => void }) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    // Trigger enter animation
    const frame = requestAnimationFrame(() => setVisible(true));
    return () => cancelAnimationFrame(frame);
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      setVisible(false);
      setTimeout(() => onDismiss(toast.id), 200);
    }, TOAST_DURATION_MS);
    return () => clearTimeout(timer);
  }, [toast.id, onDismiss]);

  const variantStyles: Record<ToastVariant, string> = {
    error: "border-destructive/50 bg-destructive/10 text-destructive",
    success: "border-green-500/50 bg-green-50 text-green-800 dark:bg-green-950 dark:text-green-200",
    info: "border-border bg-card text-foreground",
  };

  return (
    <div
      role="alert"
      aria-live="assertive"
      className={cn(
        "pointer-events-auto w-full max-w-sm rounded-lg border px-4 py-3 shadow-lg transition-all duration-200",
        variantStyles[toast.variant],
        visible ? "translate-y-0 opacity-100" : "translate-y-2 opacity-0"
      )}
    >
      <div className="flex items-start gap-3">
        <p className="flex-1 text-sm font-medium">{toast.message}</p>
        <button
          onClick={() => {
            setVisible(false);
            setTimeout(() => onDismiss(toast.id), 200);
          }}
          className="shrink-0 rounded p-0.5 opacity-70 hover:opacity-100 transition-opacity"
          aria-label="Dismiss notification"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M18 6 6 18" />
            <path d="m6 6 12 12" />
          </svg>
        </button>
      </div>
    </div>
  );
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const showToast = useCallback((message: string, variant: ToastVariant = "error") => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
    setToasts((prev) => [...prev, { id, message, variant }]);
  }, []);

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      {/* Toast container - fixed bottom-right */}
      <div
        className="pointer-events-none fixed bottom-4 right-4 z-50 flex flex-col gap-2"
        aria-label="Notifications"
      >
        {toasts.map((toast) => (
          <ToastItem key={toast.id} toast={toast} onDismiss={dismissToast} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}
