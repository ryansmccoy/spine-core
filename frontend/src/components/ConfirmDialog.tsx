import { Button, Modal } from './UI';

interface ConfirmDialogProps {
  title: string;
  message: string;
  detail?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'danger' | 'primary';
  isPending?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Reusable confirmation dialog for destructive/important actions.
 * Shows what will happen and requires explicit confirmation.
 */
export default function ConfirmDialog({
  title,
  message,
  detail,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'danger',
  isPending = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  return (
    <Modal title={title} onClose={onCancel}>
      <div className="space-y-3">
        <p className="text-sm text-gray-700">{message}</p>
        {detail && (
          <p className="text-xs text-gray-500 bg-gray-50 rounded p-2 font-mono">
            {detail}
          </p>
        )}
      </div>
      <div className="flex justify-end gap-2 mt-5">
        <Button variant="secondary" onClick={onCancel} disabled={isPending}>
          {cancelLabel}
        </Button>
        <Button
          variant={variant === 'danger' ? 'danger' : 'primary'}
          onClick={onConfirm}
          disabled={isPending}
        >
          {isPending ? 'Processing…' : confirmLabel}
        </Button>
      </div>
    </Modal>
  );
}
