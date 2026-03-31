import { z } from "zod";

const envSchema = z.object({
  NEXT_PUBLIC_API_URL: z.string().url().default("http://localhost:8000"),
  NODE_ENV: z
    .enum(["development", "test", "production"])
    .default("development"),
});

function getEnv() {
  // Client-side: NEXT_PUBLIC_ vars are inlined at build time
  // Server-side: read from process.env
  const raw = {
    NEXT_PUBLIC_API_URL:
      process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
    NODE_ENV: process.env.NODE_ENV || "development",
  };

  const parsed = envSchema.safeParse(raw);
  if (!parsed.success) {
    console.error("Invalid environment variables:", parsed.error.flatten());
    // Return defaults rather than crashing
    return {
      NEXT_PUBLIC_API_URL: "http://localhost:8000",
      NODE_ENV: "development" as const,
    };
  }
  return parsed.data;
}

export const env = getEnv();

/** Base URL for the backend API (no trailing slash) */
export const API_BASE_URL = env.NEXT_PUBLIC_API_URL;
