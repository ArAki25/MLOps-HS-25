import { serve } from "https://deno.land/std@0.224.0/http/server.ts";
import { createClient, SupabaseClient } from "https://esm.sh/@supabase/supabase-js@2.42.7";

type Order = {
  id: string;
  title: string;
  description: string | null;
  location: string | null;
  budget: number | null;
  created_at: string;
};

type Company = {
  id: string;
  name: string;
  email: string;
  score_threshold: number | null;
  max_items_per_mail: number | null;
  regions: string[] | null;
  services: string[] | null;
};

type NotificationState = {
  company_id: string;
  last_seen_prediction_at: string | null;
  last_weekly_sent_at: string | null;
};

type ModelResponse = {
  decision: "good" | "bad";
  score: number | null;
};

type Mode = "instant" | "weekly";

const env = {
  SUPABASE_URL: Deno.env.get("SUPABASE_URL"),
  SUPABASE_SERVICE_ROLE_KEY: Deno.env.get("SUPABASE_SERVICE_ROLE_KEY"),
  MODEL_URL: Deno.env.get("MODEL_URL"),
  MODEL_API_KEY: Deno.env.get("MODEL_API_KEY"),
  RESEND_API_KEY: Deno.env.get("RESEND_API_KEY"),
  MAIL_FROM: Deno.env.get("MAIL_FROM"),
};

function assertEnv(): asserts env is Record<keyof typeof env, string> {
  const missing = Object.entries(env)
    .filter(([, value]) => !value)
    .map(([key]) => key);
  if (missing.length > 0) {
    throw new Error(`Missing environment variables: ${missing.join(", ")}`);
  }
}

function supabaseClient(): SupabaseClient {
  assertEnv();
  return createClient(env.SUPABASE_URL, env.SUPABASE_SERVICE_ROLE_KEY, {
    auth: { autoRefreshToken: false, persistSession: false },
  });
}

async function withRetry<T>(fn: () => Promise<T>, attempts = 3, delayMs = 300): Promise<T> {
  let lastError: unknown;
  for (let i = 0; i < attempts; i++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;
      if (i < attempts - 1) {
        await new Promise((resolve) => setTimeout(resolve, delayMs));
      }
    }
  }
  throw lastError;
}

async function classifyOrder(company: Company, order: Order): Promise<ModelResponse> {
  assertEnv();
  const body = {
    company: {
      id: company.id,
      name: company.name,
      regions: company.regions,
      services: company.services,
      score_threshold: company.score_threshold,
    },
    order: {
      id: order.id,
      title: order.title,
      description: order.description,
      location: order.location,
      budget: order.budget,
      created_at: order.created_at,
    },
  };

  return await withRetry(async () => {
    const response = await fetch(env.MODEL_URL, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${env.MODEL_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`Model request failed: ${response.status} ${text}`);
    }

    const result = (await response.json()) as ModelResponse;
    if (!result.decision) {
      throw new Error("Model response missing decision");
    }
    return result;
  });
}

async function sendEmail(to: string, subject: string, html: string): Promise<void> {
  assertEnv();
  await withRetry(async () => {
    const response = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${env.RESEND_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        from: env.MAIL_FROM,
        to: [to],
        subject,
        html,
      }),
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`Email send failed: ${response.status} ${text}`);
    }
  });
}

function formatOrderList(orders: Array<Order & { score: number | null }>): string {
  if (orders.length === 0) {
    return "<p>Keine passenden Aufträge gefunden.</p>";
  }

  const items = orders
    .map((order) => {
      const scoreText = order.score !== null ? `Score: ${order.score.toFixed(2)}` : "Score: n/a";
      return `
        <li>
          <strong>${order.title}</strong><br/>
          ${order.description ?? "Keine Beschreibung"}<br/>
          Region: ${order.location ?? "Unbekannt"} | Budget: ${order.budget ?? "n/a"} | ${scoreText}<br/>
          Erstellt am: ${new Date(order.created_at).toLocaleString("de-CH")}
        </li>
      `;
    })
    .join("\n");

  return `<ul>${items}</ul>`;
}

async function fetchNotificationState(client: SupabaseClient, companyId: string): Promise<NotificationState | null> {
  const { data, error } = await client
    .from("notification_state")
    .select("company_id,last_seen_prediction_at,last_weekly_sent_at")
    .eq("company_id", companyId)
    .maybeSingle();

  if (error) throw error;
  return data ?? null;
}

async function updateNotificationState(
  client: SupabaseClient,
  state: NotificationState,
): Promise<void> {
  const { error } = await client.from("notification_state").upsert(state, {
    onConflict: "company_id",
  });
  if (error) throw error;
}

function shouldIncludeScore(score: number | null, threshold: number | null): boolean {
  if (score === null || threshold === null) return true;
  return score >= threshold;
}

async function fetchOrdersSince(client: SupabaseClient, since?: string): Promise<Order[]> {
  let query = client.from("orders").select("id,title,description,location,budget,created_at");
  if (since) {
    query = query.gt("created_at", since);
  }
  query = query.order("created_at", { ascending: true });
  const { data, error } = await query;
  if (error) throw error;
  return data ?? [];
}

async function fetchOrdersFromLastDays(client: SupabaseClient, days: number): Promise<Order[]> {
  const since = new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString();
  const { data, error } = await client
    .from("orders")
    .select("id,title,description,location,budget,created_at")
    .gte("created_at", since)
    .order("created_at", { ascending: true });
  if (error) throw error;
  return data ?? [];
}

async function classifyOrdersForCompany(company: Company, orders: Order[]): Promise<Array<Order & { score: number | null }>> {
  const results: Array<Order & { score: number | null }> = [];
  for (const order of orders) {
    const prediction = await classifyOrder(company, order);
    if (prediction.decision === "good" && shouldIncludeScore(prediction.score, company.score_threshold)) {
      results.push({ ...order, score: prediction.score });
    }
  }
  return results;
}

async function processInstantMode(client: SupabaseClient, company: Company): Promise<{ companyId: string; success: boolean; error?: string }> {
  try {
    const state = await fetchNotificationState(client, company.id);
    const since = state?.last_seen_prediction_at ?? null;
    const orders = await fetchOrdersSince(client, since ?? undefined);
    if (orders.length === 0) {
      return { companyId: company.id, success: true };
    }

    const goodOrders = await classifyOrdersForCompany(company, orders);
    if (goodOrders.length === 0) {
      const latestSeen = orders[orders.length - 1].created_at;
      await updateNotificationState(client, {
        company_id: company.id,
        last_seen_prediction_at: latestSeen,
        last_weekly_sent_at: state?.last_weekly_sent_at ?? null,
      });
      return { companyId: company.id, success: true };
    }

    const sorted = [...goodOrders].sort((a, b) => {
      if (a.score !== null && b.score !== null && a.score !== b.score) {
        return b.score - a.score;
      }
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    });
    const limit = company.max_items_per_mail ?? sorted.length;
    const limited = sorted.slice(0, limit);

    const html = `
      <p>Neue passende Aufträge:</p>
      ${formatOrderList(limited)}
    `;
    await sendEmail(company.email, "Neue passende Aufträge", html);

    const latestSeen = orders[orders.length - 1].created_at;
    await updateNotificationState(client, {
      company_id: company.id,
      last_seen_prediction_at: latestSeen,
      last_weekly_sent_at: state?.last_weekly_sent_at ?? null,
    });

    return { companyId: company.id, success: true };
  } catch (error) {
    console.error(`Instant mode failed for company ${company.id}:`, error);
    return { companyId: company.id, success: false, error: (error as Error).message };
  }
}

async function findRecentGoodOrders(
  client: SupabaseClient,
  company: Company,
  days: number,
  limit: number,
): Promise<Array<Order & { score: number | null }>> {
  const orders = await fetchOrdersFromLastDays(client, days);
  const goodOrders = await classifyOrdersForCompany(company, orders);
  const sorted = [...goodOrders].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
  return sorted.slice(0, limit);
}

async function processWeeklyMode(client: SupabaseClient, company: Company): Promise<{ companyId: string; success: boolean; error?: string }> {
  try {
    const state = await fetchNotificationState(client, company.id);
    const lastWeekly = state?.last_weekly_sent_at ? new Date(state.last_weekly_sent_at) : null;
    const now = new Date();
    if (lastWeekly && now.getTime() - lastWeekly.getTime() < 7 * 24 * 60 * 60 * 1000) {
      return { companyId: company.id, success: true };
    }

    const recentGood = await findRecentGoodOrders(client, company, 7, company.max_items_per_mail ?? 5);
    if (recentGood.length > 0) {
      // Good orders exist; no reminder needed.
      await updateNotificationState(client, {
        company_id: company.id,
        last_seen_prediction_at: state?.last_seen_prediction_at ?? null,
        last_weekly_sent_at: now.toISOString(),
      });
      return { companyId: company.id, success: true };
    }

    const lastGoodOrders = await findRecentGoodOrders(client, company, 30, 5);
    const html = `
      <p>In den letzten 7 Tagen wurden keine passenden Aufträge gefunden.</p>
      <p>Letzte gute Aufträge:</p>
      ${formatOrderList(lastGoodOrders)}
    `;

    await sendEmail(company.email, "Erinnerung: Keine neuen Aufträge", html);

    await updateNotificationState(client, {
      company_id: company.id,
      last_seen_prediction_at: state?.last_seen_prediction_at ?? null,
      last_weekly_sent_at: now.toISOString(),
    });

    return { companyId: company.id, success: true };
  } catch (error) {
    console.error(`Weekly mode failed for company ${company.id}:`, error);
    return { companyId: company.id, success: false, error: (error as Error).message };
  }
}

async function handleRequest(req: Request): Promise<Response> {
  try {
    if (req.method !== "GET") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const { searchParams } = new URL(req.url);
    const modeParam = searchParams.get("mode") as Mode | null;
    const mode: Mode = modeParam === "weekly" ? "weekly" : "instant";

    const client = supabaseClient();
    const { data: companies, error } = await client
      .from("companies")
      .select("id,name,email,score_threshold,max_items_per_mail,regions,services");
    if (error) throw error;

    const results = await Promise.all(
      (companies ?? []).map((company) =>
        mode === "instant"
          ? processInstantMode(client, company as Company)
          : processWeeklyMode(client, company as Company)
      ),
    );

    const failed = results.filter((r) => !r.success);
    const status = failed.length === 0 ? 200 : 207;

    return new Response(JSON.stringify({ mode, results }), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  } catch (error) {
    console.error("Request handling failed:", error);
    return new Response(JSON.stringify({ error: (error as Error).message }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }
}

serve(handleRequest);
