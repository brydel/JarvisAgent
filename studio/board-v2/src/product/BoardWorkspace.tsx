import { ReactFlowProvider } from "@xyflow/react";
import { Board } from "../Board";
import type { Source } from "../api";
export default function BoardWorkspace({ source, charge }: { source: Source; charge?: number }) {
  return <ReactFlowProvider><Board source={source} charge={charge}/></ReactFlowProvider>;
}
