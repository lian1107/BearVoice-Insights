import { EnterpriseRouter, type UiPermission } from "./router";


const DEMO_PERMISSIONS: UiPermission[] = [
  "read_voice",
  "manage_sources",
  "review_taxonomy",
  "review_opportunity",
  "manage_evaluation",
  "admin",
];


export function App() {
  return <EnterpriseRouter permissions={DEMO_PERMISSIONS} />;
}
