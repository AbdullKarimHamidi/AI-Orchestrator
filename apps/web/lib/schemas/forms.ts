import { z } from "zod"

export const workspaceFormSchema = z.object({
  name: z.string().trim().min(1, "Name is required").max(120),
  budget: z
    .string()
    .trim()
    .refine((v) => v === "" || (/^\d+(\.\d{1,2})?$/.test(v) && Number(v) <= 1_000_000), "Enter an amount in USD, or leave empty for no budget"),
})
