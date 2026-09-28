import { z } from 'zod';

// Mirrors the implemented backend HealthResponse. Domain validation lives in
// backend/contracts.py; generate API types as the business endpoints are added.
export const healthSchema = z.object({
  status: z.literal('ok'),
  database: z.literal('connected'),
});
