import type { WorkflowStep } from '../types/api';

interface StepGraphProps {
  steps: WorkflowStep[];
}

/**
 * Linear DAG step graph for workflow visualization.
 * Renders steps left-to-right with arrows based on depends_on.
 * For the v1 workflows (all linear chains), this uses CSS flex + SVG arrows.
 */
export default function StepGraph({ steps }: StepGraphProps) {
  if (!steps.length) {
    return <div className="text-sm text-gray-400">No steps defined</div>;
  }

  return (
    <div className="overflow-x-auto py-4">
      <div className="flex items-center gap-1 min-w-max">
        {steps.map((step, i) => {
          const hasDeps = step.depends_on && step.depends_on.length > 0;
          return (
            <div key={step.name} className="flex items-center">
              {/* Arrow from previous step */}
              {i > 0 && (
                <svg width="32" height="24" className="shrink-0" viewBox="0 0 32 24">
                  <line x1="0" y1="12" x2="24" y2="12" stroke="#94a3b8" strokeWidth="2" />
                  <polygon points="24,7 32,12 24,17" fill="#94a3b8" />
                </svg>
              )}
              {/* Step node */}
              <div className="relative group">
                <div className="bg-white border-2 border-spine-300 rounded-lg px-4 py-2.5 min-w-[120px] text-center hover:border-spine-500 hover:shadow-md transition-all cursor-default">
                  <div className="text-sm font-semibold text-gray-800">{step.name}</div>
                  {step.pipeline && (
                    <div className="text-[10px] text-gray-400 mt-0.5 truncate max-w-[140px]">
                      {step.pipeline}
                    </div>
                  )}
                </div>
                {/* Tooltip with description + depends_on */}
                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden group-hover:block z-20">
                  <div className="bg-gray-900 text-white text-xs rounded-lg px-3 py-2 shadow-lg max-w-[200px]">
                    {step.description && (
                      <p className="mb-1">{step.description}</p>
                    )}
                    {hasDeps && (
                      <p className="text-gray-400">
                        depends on: {step.depends_on.join(', ')}
                      </p>
                    )}
                    {!step.description && !hasDeps && (
                      <p className="text-gray-400">No description</p>
                    )}
                    {/* Arrow pointing down */}
                    <div className="absolute left-1/2 -translate-x-1/2 top-full w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-gray-900" />
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
