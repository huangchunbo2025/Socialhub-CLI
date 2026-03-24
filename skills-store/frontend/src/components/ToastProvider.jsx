import { createContext, useContext, useMemo, useState } from "react";

const ToastContext = createContext(null);

export function ToastProvider({ children }) {
  const [toast, setToast] = useState(null);

  const value = useMemo(
    () => ({
      show(message, tone = "default") {
        setToast({ message, tone });
        window.clearTimeout(window.__skillsStoreToastTimer);
        window.__skillsStoreToastTimer = window.setTimeout(() => setToast(null), 2600);
      }
    }),
    []
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      {toast ? <div className={`toast toast-${toast.tone}`}>{toast.message}</div> : null}
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used inside ToastProvider");
  }
  return context;
}
