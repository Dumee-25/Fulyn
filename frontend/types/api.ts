export type HealthStatus = "ok" | "degraded";

export interface HealthResponse {
  status: HealthStatus;
  app: string;
  version: string;
  environment: string;
  database: "ok" | "unavailable";
  timezone: string;
  currency: string;
}
