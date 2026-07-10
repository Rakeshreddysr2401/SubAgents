import type { ActionRequest, ResumeDecision } from "../../../api/types";

/** Contract every rich interrupt component implements. The registry maps an
 * action name ("component id") to one of these; anything unregistered falls
 * back to the generic JSON card. */
export interface InterruptItemProps {
  request: ActionRequest;
  decided: ResumeDecision | null;
  disabled: boolean;
  onDecide: (decision: ResumeDecision) => void;
}
