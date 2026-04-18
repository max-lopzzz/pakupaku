/**
 * Round to nearest whole number (for calories, macro grams, day totals).
 */
export const round0 = (n: number | null | undefined): number =>
  Math.round(n ?? 0);

/**
 * Round to one decimal place (for weight, height, body-fat %, shopping amounts).
 */
export const round1 = (n: number | null | undefined): number =>
  Math.round((n ?? 0) * 10) / 10;
