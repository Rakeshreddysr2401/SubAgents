/** Turn a snake_case tool name (`get_current_location`) into a human label
 * (`get current location`) for display in activity trails and interrupt cards. */
export function friendlyToolName(name: string): string {
  return name.replace(/_/g, " ");
}
