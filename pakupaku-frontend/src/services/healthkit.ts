/**
 * healthkit.ts
 * iOS-only HealthKit integration — reads active calories burned for a given date.
 * Safely no-ops on Android / web where the plugin is unavailable.
 */

import { Capacitor } from "@capacitor/core";

// Only import the plugin on iOS to avoid crashing on other platforms
async function _getPlugin() {
  if (Capacitor.getPlatform() !== "ios") return null;
  try {
    // eslint-disable-next-line @typescript-eslint/ban-ts-comment
    // @ts-ignore — optional peer dependency, only present on iOS builds
    const { CapacitorHealthkit } = await import("@perfood/capacitor-healthkit");
    return CapacitorHealthkit;
  } catch {
    return null;
  }
}

export const isHealthKitAvailable = Capacitor.getPlatform() === "ios";

/**
 * Request HealthKit read permission for active energy burned.
 * Safe to call multiple times — iOS only shows the prompt once.
 */
export async function requestHealthKitPermission(): Promise<boolean> {
  const plugin = await _getPlugin();
  if (!plugin) return false;
  try {
    await plugin.requestAuthorization({
      all:   [],
      read:  ["calories"],
      write: [],
    });
    return true;
  } catch {
    return false;
  }
}

/**
 * Returns total active calories burned on the given date (YYYY-MM-DD).
 * Returns null if unavailable or permission denied.
 */
export async function getActiveCaloriesForDate(date: string): Promise<number | null> {
  const plugin = await _getPlugin();
  if (!plugin) return null;
  try {
    const startDate = new Date(date + "T00:00:00").toISOString();
    const endDate   = new Date(date + "T23:59:59").toISOString();

    const result: any = await plugin.queryHKitSampleType({
      sampleName: "calories",
      startDate,
      endDate,
      limit: 0,
    });

    const samples: any[] = result.output ?? [];
    const total = samples.reduce((sum, s) => sum + (s.value ?? 0), 0);
    return total > 0 ? Math.round(total) : null;
  } catch {
    return null;
  }
}
