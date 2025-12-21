/**
 * Resizable split panel using react-resizable-panels.
 * Wraps Group / Panel / Separator for a consistent look.
 */

import { Group, Panel, Separator } from 'react-resizable-panels';

interface SplitPanelProps {
  /** Direction of the split */
  direction?: 'vertical' | 'horizontal';
  /** Content for the top (or left) panel */
  top: React.ReactNode;
  /** Content for the bottom (or right) panel */
  bottom: React.ReactNode;
  /** Default size of the top panel (percent, default 50) */
  defaultTopSize?: number;
  /** Minimum size of either panel (percent, default 20) */
  minSize?: number;
  /** CSS class applied to the outer container */
  className?: string;
}

export default function SplitPanel({
  direction = 'vertical',
  top,
  bottom,
  defaultTopSize = 50,
  minSize = 20,
  className = '',
}: SplitPanelProps) {
  return (
    <Group
      orientation={direction}
      className={`rounded-lg border border-gray-200 bg-white overflow-hidden ${className}`}
    >
      <Panel defaultSize={`${defaultTopSize}%`} minSize={`${minSize}%`} className="overflow-auto">
        {top}
      </Panel>
      <Separator
        className={`
          flex items-center justify-center
          ${direction === 'vertical'
            ? 'h-2 cursor-row-resize hover:bg-spine-50 bg-gray-100 border-y border-gray-200'
            : 'w-2 cursor-col-resize hover:bg-spine-50 bg-gray-100 border-x border-gray-200'}
          transition-colors
        `}
      >
        <div
          className={`rounded-full bg-gray-300 ${
            direction === 'vertical' ? 'w-8 h-0.5' : 'h-8 w-0.5'
          }`}
        />
      </Separator>
      <Panel defaultSize={`${100 - defaultTopSize}%`} minSize={`${minSize}%`} className="overflow-auto">
        {bottom}
      </Panel>
    </Group>
  );
}
