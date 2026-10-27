export interface ToastData {
  id: number;
  text: string;
}

/** NYT-style transient black pill over the app bar. Re-animates per toast id. */
export function Toast({ toast }: { toast: ToastData | null }) {
  if (!toast) return null;
  return (
    <div key={toast.id} className="toast" role="status">
      {toast.text}
    </div>
  );
}
