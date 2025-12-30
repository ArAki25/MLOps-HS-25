// ============================================================================
// Supabase Edge Function: SIMAP Sync v8 - Performance & Reliability
// ============================================================================
//
// VERBESSERUNGEN in v8:
// - #3: Bessere Fehlerbehandlung (404 vs 503 unterscheiden)
// - #4: N+1 Query Fix (Batch-Update statt einzelne Queries)
// - #5: Parallele API-Calls (4 concurrent statt sequentiell)
// - #7: Größere Batch-Size (500 statt 100)
// - #8: content_hash wird jetzt tatsächlich genutzt
// - #9: Robusteres Date-Parsing mit Validierung
// - "Stuck-in-the-Past" Fix: 404-Fehler markieren detail_fetched_at
//
// LOGIK:
// - last_checked_at = Wann wurde das Projekt zuletzt in Search API gesehen
// - detail_fetched_at = Wann wurden Details zuletzt geholt
//
// ============================================================================
// CRON SETUP - WICHTIG FÜR KORREKTE KONFIGURATION
// ============================================================================
//
// JOB 1: HOURLY SYNC (neue Projekte finden)
// -----------------------------------------
// Cron: '5 * * * *' (jede Stunde um :05)
// URL:  ?mode=hourly
// Zweck: Findet neue Projekte, holt sofort Details für diese
//
// JOB 2: REFRESH SYNC (bestehende Daten aktualisieren)
// ----------------------------------------------------
// Cron: '30 */4 * * *' (alle 4 Stunden um :30)
// URL:  ?mode=refresh&detail_max_age_hours=168&refresh_limit=750
//
// WICHTIG: detail_max_age_hours MUSS größer sein als die Zeit die benötigt
// wird um ALLE Projekte durchzugehen! Sonst rotieren immer die gleichen.
//
// Rechnung für "alle Projekte 1x pro Woche":
// - 10.000 Projekte in DB
// - 6 Aufrufe/Tag (alle 4h) × 750 = 4.500/Tag
// - 4.500 × 7 Tage = 31.500 → Genug Kapazität
// - detail_max_age_hours=168 (7 Tage) → Projekte fallen erst nach 7 Tagen
//   zurück in die Queue
//
// ============================================================================

import { serve } from "https://deno.land/std@0.168.0/http/server.ts"
import { createClient, SupabaseClient } from 'https://esm.sh/@supabase/supabase-js@2'

// ============================================================================
// CONFIG
// ============================================================================

const SIMAP_API_BASE = "https://www.simap.ch/api"
const SEARCH_ENDPOINT = "/publications/v2/project/project-search"
const DETAIL_ENDPOINT = "/publications/v1/project"

const DELAY_SEARCH_MS = 100
const DELAY_DETAIL_MS = 150
const DETAIL_CONCURRENCY = 4  // Parallele Detail-Requests
const BATCH_SIZE = 500  // Erhöht von 100

const DEFAULT_CANTONS = [
  "ZH", "BE", "LU", "UR", "SZ", "OW", "NW", "GL", "ZG",
  "SO", "BS", "BL", "SH", "AR", "AI", "SG", "GR", "AG", "TG",
]

const PUB_TYPES_WITH_DETAILS = [
  'tender', 'award', 'direct_award', 'competition',
  'study_contract', 'participant_selection', 'selective_offering_phase',
]

// ============================================================================
// TYPES
// ============================================================================

type SyncMode = 'hourly' | 'refresh' | 'full'

interface SyncConfig {
  mode: SyncMode
  hoursBack: number
  daysBack: number
  refreshLimit: number
  detailMaxAgeHours: number
  cantons: string[]
  skipDetails: boolean
}

interface SyncStats {
  mode: SyncMode
  fetched: number
  new_projects: number
  updated_projects: number
  skipped_projects: number
  details_fetched: number
  details_skipped: number
  details_errors: number
  details_not_found: number  // NEU: 404 separat zählen
  duration_seconds: number
}

// #3: Bessere Fehlerbehandlung - Fehlertypen unterscheiden
type FetchErrorType = 'not_found' | 'auth' | 'server_error' | 'rate_limit' | 'network'

interface FetchResult {
  success: boolean
  data?: Record<string, unknown>
  error?: {
    type: FetchErrorType
    message: string
    retryable: boolean
  }
}

interface WinnerData {
  vendor_id: string | null
  name: string | null
  street: string | null
  city: string | null
  postal_code: string | null
  canton: string | null
  country: string | null
  price: number | null
  currency: string | null
  vat_type: string | null
}

interface ProjectRecord {
  // IDs
  simap_project_id: string
  simap_publication_id: string | null
  project_number: string | null
  publication_number: string | null
  
  // Content
  title_de: string | null
  title_fr: string | null
  description_de: string | null
  description_fr: string | null
  
  // Dates
  publication_date: string
  submission_deadline: string | null
  offer_opening_date: string | null
  award_decision_date: string | null
  
  // Classification
  pub_type: string
  project_type: string | null
  project_subtype: string | null
  process_type: string | null
  order_type: string | null
  lots_type: string | null
  lots_count: number
  corrected: boolean
  
  // Location
  canton: string | null
  city: string | null
  postal_code: string | null
  country: string
  
  // Codes
  cpv_code_main: string | null
  cpv_codes: string[]
  bkp_codes: string[]
  oag_codes: string[]
  
  // Proc Office
  proc_office_id: string | null
  proc_office_name_de: string | null
  proc_office_name_fr: string | null
  proc_office_street: string | null
  proc_office_city: string | null
  proc_office_postal_code: string | null
  proc_office_canton: string | null
  proc_office_email: string | null
  proc_office_phone: string | null
  proc_office_contact: string | null
  
  // Recipient
  recipient_name: string | null
  recipient_city: string | null
  recipient_canton: string | null
  
  // Award
  winner_id: string | null
  winner_name: string | null
  winner_street: string | null
  winner_city: string | null
  winner_postal_code: string | null
  winner_canton: string | null
  award_amount: number | null
  award_currency: string | null
  award_vat_type: string | null
  number_of_submissions: number | null
  all_winners: WinnerData[] | null
  award_justification_de: string | null
  remedies_notice_de: string | null
  total_price_selection: string | null
  
  // References
  referencing_pub_id: string | null
  referencing_pub_type: string | null
  referencing_pub_date: string | null
  referencing_pub_number: string | null
  
  // Construction
  construction_type: string | null
  construction_category: string | null
  
  // Metadata
  publication_ted: boolean
  state_contract_area: boolean
  creation_language: string | null
  has_project_documents: boolean
  
  // Tracking
  content_hash: string
  last_checked_at: string
  detail_fetched_at: string | null
  
  // Raw
  raw_json_search: unknown
  raw_json_detail: unknown | null
}

// ============================================================================
// HELPERS
// ============================================================================

function getString(obj: unknown, ...keys: string[]): string | null {
  if (!obj || typeof obj !== 'object') return null
  let current: unknown = obj
  for (const key of keys) {
    if (!current || typeof current !== 'object') return null
    current = (current as Record<string, unknown>)[key]
  }
  return typeof current === 'string' ? current : null
}

function getNumber(obj: unknown, ...keys: string[]): number | null {
  if (!obj || typeof obj !== 'object') return null
  let current: unknown = obj
  for (const key of keys) {
    if (!current || typeof current !== 'object') return null
    current = (current as Record<string, unknown>)[key]
  }
  if (typeof current === 'number') return current
  if (typeof current === 'string') {
    const parsed = parseFloat(current.replace(/'/g, '').replace(/,/g, ''))
    return isNaN(parsed) ? null : parsed
  }
  return null
}

function getBool(obj: unknown, ...keys: string[]): boolean {
  if (!obj || typeof obj !== 'object') return false
  let current: unknown = obj
  for (const key of keys) {
    if (!current || typeof current !== 'object') return false
    current = (current as Record<string, unknown>)[key]
  }
  return current === true
}

function getTrans(obj: unknown, lang: 'de' | 'fr'): string | null {
  if (!obj || typeof obj !== 'object') return null
  return (obj as Record<string, unknown>)[lang] as string || null
}

function getTransAny(obj: unknown): string | null {
  if (!obj || typeof obj !== 'object') return null
  const o = obj as Record<string, unknown>
  return (o.de || o.fr || o.it || o.en) as string || null
}

// #9: Robusteres Date-Parsing mit Validierung
function parseDate(d: unknown): string | null {
  if (!d) return null
  if (typeof d !== 'string') return null
  
  try {
    // ISO-Format direkt parsen
    const date = new Date(d)
    if (isNaN(date.getTime())) return null
    
    // Validierung: Jahr muss plausibel sein (2000-2100)
    const year = date.getFullYear()
    if (year < 2000 || year > 2100) return null
    
    // ISO 8601 YYYY-MM-DD zurückgeben
    return date.toISOString().split('T')[0]
  } catch {
    return null
  }
}

function parseDateTime(d: unknown): string | null {
  if (!d) return null
  if (typeof d !== 'string') return null
  
  try {
    const date = new Date(d)
    if (isNaN(date.getTime())) return null
    
    // Validierung: Jahr muss plausibel sein
    const year = date.getFullYear()
    if (year < 2000 || year > 2100) return null
    
    return date.toISOString()
  } catch {
    return null
  }
}

function extractCode(c: unknown): string | null {
  if (typeof c === 'string') return c
  if (c && typeof c === 'object') return (c as Record<string, unknown>).code as string || null
  return null
}

function parseCodes(arr: unknown): string[] {
  if (!Array.isArray(arr)) return []
  return arr.map(extractCode).filter((c): c is string => c !== null)
}

// #8: Verbesserter Hash der tatsächlich genutzt wird
function computeContentHash(entry: Record<string, unknown>): string {
  // Hash über die wichtigsten Felder die auf Änderungen geprüft werden sollen
  const canonical = {
    id: entry.id,
    pubId: entry.publicationId,
    pubType: entry.pubType,
    pubDate: entry.publicationDate,
    projectNumber: entry.projectNumber,
    corrected: entry.corrected,
    // Title kann sich bei Korrekturen ändern - daher NICHT im Hash
  }
  
  const s = JSON.stringify(canonical)
  let h = 0
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) - h + s.charCodeAt(i)) | 0
  }
  return h.toString(16)
}

function delay(ms: number): Promise<void> {
  return new Promise(r => setTimeout(r, ms))
}

// #5: Promise Pool für parallele Ausführung mit Limit
async function runWithConcurrency<T, R>(
  items: T[],
  concurrency: number,
  fn: (item: T) => Promise<R>
): Promise<R[]> {
  const results: R[] = []
  const executing: Promise<void>[] = []
  
  for (const item of items) {
    const promise = fn(item).then(result => {
      results.push(result)
    })
    executing.push(promise)
    
    if (executing.length >= concurrency) {
      await Promise.race(executing)
      // Entferne erledigte Promises
      for (let i = executing.length - 1; i >= 0; i--) {
        const p = executing[i]
        // Check ob Promise erledigt (vereinfacht)
        const settled = await Promise.race([p.then(() => true), Promise.resolve(false)])
        if (settled) executing.splice(i, 1)
      }
    }
  }
  
  await Promise.all(executing)
  return results
}

// ============================================================================
// API
// ============================================================================

async function searchProjects(startDate: string, cantons: string[]): Promise<Record<string, unknown>[]> {
  const projects: Record<string, unknown>[] = []
  let lastItem: string | null = null
  
  while (true) {
    const params = new URLSearchParams({ newestPublicationFrom: startDate })
    if (cantons.length) params.append('orderAddressCantons', cantons.join(','))
    if (lastItem) params.set('lastItem', lastItem)
    
    const res = await fetch(`${SIMAP_API_BASE}${SEARCH_ENDPOINT}?${params}`, {
      headers: { 'Accept': 'application/json' }
    })
    if (!res.ok) throw new Error(`Search API: ${res.status}`)
    
    const data = await res.json() as { projects?: unknown[]; pagination?: { lastItem?: string } }
    const page = (data.projects || []) as Record<string, unknown>[]
    if (!page.length) break
    
    projects.push(...page)
    lastItem = data.pagination?.lastItem || null
    if (!lastItem) break
    
    await delay(DELAY_SEARCH_MS)
  }
  
  return projects
}

// #3: Verbesserte Fehlerbehandlung mit FetchResult
async function fetchDetail(projectId: string, pubId: string): Promise<FetchResult> {
  try {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 10000) // 10s Timeout
    
    const res = await fetch(
      `${SIMAP_API_BASE}${DETAIL_ENDPOINT}/${projectId}/publication-details/${pubId}`,
      { 
        headers: { 'Accept': 'application/json' },
        signal: controller.signal
      }
    )
    
    clearTimeout(timeoutId)
    
    // Differenzierte Fehlerbehandlung
    if (res.status === 404) {
      return {
        success: false,
        error: { type: 'not_found', message: 'Publikation nicht gefunden', retryable: false }
      }
    }
    
    if (res.status === 401 || res.status === 403) {
      return {
        success: false,
        error: { type: 'auth', message: `Auth error: ${res.status}`, retryable: false }
      }
    }
    
    if (res.status === 429) {
      return {
        success: false,
        error: { type: 'rate_limit', message: 'Rate limit erreicht', retryable: true }
      }
    }
    
    if (res.status >= 500) {
      return {
        success: false,
        error: { type: 'server_error', message: `Server error: ${res.status}`, retryable: true }
      }
    }
    
    if (!res.ok) {
      return {
        success: false,
        error: { type: 'server_error', message: `HTTP ${res.status}`, retryable: true }
      }
    }
    
    const data = await res.json() as Record<string, unknown>
    return { success: true, data }
    
  } catch (err) {
    const error = err as Error
    
    if (error.name === 'AbortError') {
      return {
        success: false,
        error: { type: 'network', message: 'Request timeout', retryable: true }
      }
    }
    
    return {
      success: false,
      error: { type: 'network', message: error.message, retryable: true }
    }
  }
}

// ============================================================================
// PARSING
// ============================================================================

function parseSearchResult(entry: Record<string, unknown>): ProjectRecord {
  const now = new Date().toISOString()
  const addr = entry.orderAddress as Record<string, unknown> | undefined
  const lots = entry.lots as Record<string, unknown>[] | undefined
  
  let canton = addr ? getString(addr, 'cantonId') : null
  let city = addr ? getTransAny(addr.city) : null
  let postalCode = addr ? getString(addr, 'postalCode') : null
  let country = addr ? getString(addr, 'countryId') || 'CH' : 'CH'
  
  if (!canton && lots?.length) {
    const la = lots[0].orderAddress as Record<string, unknown> | undefined
    if (la) {
      canton = getString(la, 'cantonId')
      city = getTransAny(la.city)
      postalCode = getString(la, 'postalCode')
      country = getString(la, 'countryId') || 'CH'
    }
  }
  
  let pubNum = entry.publicationNumber
  if (pubNum && typeof pubNum === 'object') pubNum = (pubNum as Record<string, unknown>).publicationNumber
  
  return {
    simap_project_id: entry.id as string,
    simap_publication_id: entry.publicationId as string || null,
    project_number: getString(entry, 'projectNumber'),
    publication_number: pubNum as string || null,
    title_de: getTrans(entry.title, 'de'),
    title_fr: getTrans(entry.title, 'fr'),
    description_de: null,
    description_fr: null,
    publication_date: parseDate(entry.publicationDate) || now.split('T')[0],
    submission_deadline: null,
    offer_opening_date: null,
    award_decision_date: null,
    pub_type: getString(entry, 'pubType') || 'unknown',
    project_type: getString(entry, 'projectType'),
    project_subtype: getString(entry, 'projectSubType'),
    process_type: getString(entry, 'processType'),
    order_type: getString(entry, 'orderType'),
    lots_type: getString(entry, 'lotsType'),
    lots_count: lots?.length || 0,
    corrected: getBool(entry, 'corrected'),
    canton,
    city,
    postal_code: postalCode,
    country,
    cpv_code_main: null,
    cpv_codes: [],
    bkp_codes: [],
    oag_codes: [],
    proc_office_id: getString(entry, 'procOfficeId'),
    proc_office_name_de: getTrans(entry.procOfficeName, 'de'),
    proc_office_name_fr: getTrans(entry.procOfficeName, 'fr'),
    proc_office_street: null,
    proc_office_city: null,
    proc_office_postal_code: null,
    proc_office_canton: null,
    proc_office_email: null,
    proc_office_phone: null,
    proc_office_contact: null,
    recipient_name: null,
    recipient_city: null,
    recipient_canton: null,
    winner_id: null,
    winner_name: null,
    winner_street: null,
    winner_city: null,
    winner_postal_code: null,
    winner_canton: null,
    award_amount: null,
    award_currency: null,
    award_vat_type: null,
    number_of_submissions: null,
    all_winners: null,
    award_justification_de: null,
    remedies_notice_de: null,
    total_price_selection: null,
    referencing_pub_id: null,
    referencing_pub_type: null,
    referencing_pub_date: null,
    referencing_pub_number: null,
    construction_type: null,
    construction_category: null,
    publication_ted: false,
    state_contract_area: false,
    creation_language: null,
    has_project_documents: false,
    content_hash: computeContentHash(entry),
    last_checked_at: now,
    detail_fetched_at: null,
    raw_json_search: entry,
    raw_json_detail: null,
  }
}

function enrichWithDetail(p: ProjectRecord, d: Record<string, unknown>): void {
  const now = new Date().toISOString()
  const base = d.base as Record<string, unknown> | undefined
  const proc = d.procurement as Record<string, unknown> | undefined
  const dates = d.dates as Record<string, unknown> | undefined
  const decision = d.decision as Record<string, unknown> | undefined
  const terms = d.terms as Record<string, unknown> | undefined
  const info = d['project-info'] as Record<string, unknown> | undefined
  const ref = d.referencingPub as Record<string, unknown> | undefined
  
  // Base
  if (base) {
    p.publication_ted = getBool(base, 'publicationTed')
    p.state_contract_area = getBool(base, 'stateContractArea')
    p.creation_language = getString(base, 'creationLanguage')
    p.referencing_pub_id = getString(base, 'referencingPubId')
  }
  
  // Procurement
  if (proc) {
    const desc = proc.orderDescription as Record<string, unknown> | undefined
    if (desc) {
      p.description_de = getTrans(desc, 'de')
      p.description_fr = getTrans(desc, 'fr')
    }
    const cpv = extractCode(proc.cpvCode)
    if (cpv) {
      p.cpv_code_main = cpv
      p.cpv_codes = [cpv, ...parseCodes(proc.additionalCpvCodes)].filter((v, i, a) => a.indexOf(v) === i)
    }
    p.bkp_codes = parseCodes(proc.bkpCodes)
    p.oag_codes = parseCodes(proc.oagCodes)
    p.order_type = p.order_type || getString(proc, 'orderType')
    p.construction_type = getString(proc, 'constructionType')
    p.construction_category = getString(proc, 'constructionCategory')
  }
  
  // Dates
  if (dates) {
    p.submission_deadline = parseDateTime(dates.offerDeadline || dates.submissionDeadline)
    p.offer_opening_date = parseDateTime(dates.offerOpening || dates.offerOpeningDate)
  }
  
  // Terms
  if (terms?.remediesNotice) {
    p.remedies_notice_de = getTrans(terms.remediesNotice, 'de')
  }
  
  // Project Info
  if (info) {
    const pa = info.procOfficeAddress as Record<string, unknown> | undefined
    if (pa) {
      p.proc_office_street = getTransAny(pa.street)
      p.proc_office_city = getTransAny(pa.city)
      p.proc_office_postal_code = getString(pa, 'postalCode')
      p.proc_office_canton = getString(pa, 'cantonId')
      p.proc_office_email = getString(pa, 'email')
      p.proc_office_phone = getString(pa, 'phone')
      p.proc_office_contact = getTransAny(pa.contactPerson)
    }
    const ra = info.procurementRecipientAddress as Record<string, unknown> | undefined
    if (ra) {
      p.recipient_name = getTransAny(ra.name)
      p.recipient_city = getTransAny(ra.city)
      p.recipient_canton = getString(ra, 'cantonId')
    }
  }
  
  // Decision (Award)
  if (decision && (p.pub_type === 'award' || p.pub_type === 'direct_award')) {
    const vendors = decision.vendors as Record<string, unknown>[] | undefined
    if (vendors?.length) {
      const winners: WinnerData[] = vendors.map(v => {
        const va = v.vendorAddress as Record<string, unknown> | undefined
        const pr = v.price as Record<string, unknown> | undefined
        return {
          vendor_id: getString(v, 'vendorId'),
          name: getString(v, 'vendorName'),
          street: va ? getString(va, 'street') : null,
          city: va ? getTransAny(va.city) : null,
          postal_code: va ? getString(va, 'postalCode') : null,
          canton: va ? getString(va, 'cantonId') : null,
          country: va ? getString(va, 'countryId') || 'CH' : null,
          price: pr ? getNumber(pr, 'price') : null,
          currency: pr ? (getString(pr, 'currency')?.toUpperCase() || 'CHF') : null,
          vat_type: pr ? getString(pr, 'vatType') : null,
        }
      })
      p.all_winners = winners
      const w = winners[0]
      p.winner_id = w.vendor_id
      p.winner_name = w.name
      p.winner_street = w.street
      p.winner_city = w.city
      p.winner_postal_code = w.postal_code
      p.winner_canton = w.canton
      p.award_amount = w.price
      p.award_currency = w.currency
      p.award_vat_type = w.vat_type
    }
    p.number_of_submissions = getNumber(decision, 'numberOfSubmissions')
    p.award_decision_date = parseDate(decision.awardDecisionDate)
    p.total_price_selection = getString(decision, 'totalPriceSelection')
    const just = decision.awardDecisionJustification as Record<string, unknown> | undefined
    if (just) p.award_justification_de = getTrans(just, 'de')
  }
  
  // Referencing Pub
  if (ref) {
    p.referencing_pub_id = p.referencing_pub_id || getString(ref, 'publicationId')
    p.referencing_pub_type = getString(ref, 'pubType')
    p.referencing_pub_date = parseDate(ref.publicationDate)
    p.referencing_pub_number = getString(ref, 'publicationNumber')
  }
  
  p.has_project_documents = getBool(d, 'hasProjectDocuments')
  p.raw_json_detail = d
  p.detail_fetched_at = now
}

// ============================================================================
// DATABASE
// ============================================================================

function key(pid: string, pubId: string | null): string {
  return `${pid}:${pubId ?? 'null'}`
}

async function getExisting(db: SupabaseClient, ids: string[]): Promise<Map<string, { detailAt: string | null, hash: string | null }>> {
  const map = new Map<string, { detailAt: string | null, hash: string | null }>()
  for (let i = 0; i < ids.length; i += 500) {
    const { data } = await db.from('projects')
      .select('simap_project_id, simap_publication_id, detail_fetched_at, content_hash')
      .in('simap_project_id', ids.slice(i, i + 500))
    if (data) {
      for (const r of data) {
        map.set(key(r.simap_project_id, r.simap_publication_id), { 
          detailAt: r.detail_fetched_at,
          hash: r.content_hash 
        })
      }
    }
  }
  return map
}

async function getProjectsNeedingDetails(
  db: SupabaseClient,
  maxAgeHours: number,
  limit: number
): Promise<{ simap_project_id: string; simap_publication_id: string | null; pub_type: string }[]> {
  const cutoff = new Date()
  cutoff.setHours(cutoff.getHours() - maxAgeHours)
  
  const { data } = await db.from('projects')
    .select('simap_project_id, simap_publication_id, pub_type')
    .in('pub_type', PUB_TYPES_WITH_DETAILS)
    .or(`detail_fetched_at.is.null,detail_fetched_at.lt.${cutoff.toISOString()}`)
    .order('detail_fetched_at', { ascending: true, nullsFirst: true })
    .limit(limit)
  
  return data || []
}

// #7: Erhöhte Batch-Size (500 statt 100)
async function upsertProjects(db: SupabaseClient, projects: ProjectRecord[]): Promise<void> {
  for (let i = 0; i < projects.length; i += BATCH_SIZE) {
    const { error } = await db.from('projects')
      .upsert(projects.slice(i, i + BATCH_SIZE), { onConflict: 'simap_project_id,simap_publication_id' })
    if (error) throw new Error(`Upsert batch ${i}-${i + BATCH_SIZE}: ${error.message}`)
  }
}

// #4: Batch-Update statt N+1 Queries
async function updateLastChecked(db: SupabaseClient, ids: { pid: string; pubId: string | null }[]): Promise<void> {
  if (!ids.length) return
  
  const now = new Date().toISOString()
  
  // Gruppiere nach pubId null vs. nicht-null für effizientere Queries
  const withPubId = ids.filter(i => i.pubId !== null)
  const withoutPubId = ids.filter(i => i.pubId === null)
  
  // Batch-Update für Projekte MIT publication_id
  if (withPubId.length) {
    // Gruppiere in Batches von 500
    for (let i = 0; i < withPubId.length; i += 500) {
      const batch = withPubId.slice(i, i + 500)
      const projectIds = batch.map(b => b.pid)
      
      const { error } = await db.from('projects')
        .update({ last_checked_at: now })
        .in('simap_project_id', projectIds)
        .not('simap_publication_id', 'is', null)
      
      if (error) console.warn(`Batch update error: ${error.message}`)
    }
  }
  
  // Batch-Update für Projekte OHNE publication_id
  if (withoutPubId.length) {
    for (let i = 0; i < withoutPubId.length; i += 500) {
      const batch = withoutPubId.slice(i, i + 500)
      const projectIds = batch.map(b => b.pid)
      
      const { error } = await db.from('projects')
        .update({ last_checked_at: now })
        .in('simap_project_id', projectIds)
        .is('simap_publication_id', null)
      
      if (error) console.warn(`Batch update error: ${error.message}`)
    }
  }
}

// NEU: Markiert ein Projekt als "versucht" ohne Daten zu ändern
// Verhindert "Stuck-in-the-Past" bei permanenten 404-Fehlern
async function markDetailAttempted(
  db: SupabaseClient, 
  projectId: string, 
  pubId: string | null
): Promise<void> {
  const now = new Date().toISOString()
  
  let query = db.from('projects')
    .update({ detail_fetched_at: now })
    .eq('simap_project_id', projectId)
  
  if (pubId === null) {
    query = query.is('simap_publication_id', null)
  } else {
    query = query.eq('simap_publication_id', pubId)
  }
  
  await query
}

async function updateDetails(db: SupabaseClient, p: ProjectRecord): Promise<void> {
  const updateData: Record<string, unknown> = {
    description_de: p.description_de,
    description_fr: p.description_fr,
    cpv_code_main: p.cpv_code_main,
    cpv_codes: p.cpv_codes,
    bkp_codes: p.bkp_codes,
    oag_codes: p.oag_codes,
    order_type: p.order_type,
    submission_deadline: p.submission_deadline,
    offer_opening_date: p.offer_opening_date,
    proc_office_street: p.proc_office_street,
    proc_office_city: p.proc_office_city,
    proc_office_postal_code: p.proc_office_postal_code,
    proc_office_canton: p.proc_office_canton,
    proc_office_email: p.proc_office_email,
    proc_office_phone: p.proc_office_phone,
    proc_office_contact: p.proc_office_contact,
    recipient_name: p.recipient_name,
    recipient_city: p.recipient_city,
    recipient_canton: p.recipient_canton,
    winner_id: p.winner_id,
    winner_name: p.winner_name,
    winner_street: p.winner_street,
    winner_city: p.winner_city,
    winner_postal_code: p.winner_postal_code,
    winner_canton: p.winner_canton,
    award_amount: p.award_amount,
    award_currency: p.award_currency,
    award_vat_type: p.award_vat_type,
    number_of_submissions: p.number_of_submissions,
    award_decision_date: p.award_decision_date,
    all_winners: p.all_winners,
    award_justification_de: p.award_justification_de,
    remedies_notice_de: p.remedies_notice_de,
    total_price_selection: p.total_price_selection,
    referencing_pub_id: p.referencing_pub_id,
    referencing_pub_type: p.referencing_pub_type,
    referencing_pub_date: p.referencing_pub_date,
    referencing_pub_number: p.referencing_pub_number,
    construction_type: p.construction_type,
    construction_category: p.construction_category,
    publication_ted: p.publication_ted,
    state_contract_area: p.state_contract_area,
    creation_language: p.creation_language,
    has_project_documents: p.has_project_documents,
    raw_json_detail: p.raw_json_detail,
    detail_fetched_at: p.detail_fetched_at,
  }
  
  let query = db.from('projects').update(updateData).eq('simap_project_id', p.simap_project_id)
  
  if (p.simap_publication_id === null) {
    query = query.is('simap_publication_id', null)
  } else {
    query = query.eq('simap_publication_id', p.simap_publication_id)
  }
  
  const { error } = await query
  if (error) console.warn(`Update detail error: ${error.message}`)
}

// ============================================================================
// SYNC MODES
// ============================================================================

async function syncHourly(db: SupabaseClient, config: SyncConfig, stats: SyncStats): Promise<void> {
  const start = new Date()
  start.setHours(start.getHours() - config.hoursBack)
  const startStr = start.toISOString().split('T')[0]
  
  console.log(`[HOURLY] Since ${startStr}`)
  
  const raw = await searchProjects(startStr, config.cantons)
  stats.fetched = raw.length
  if (!raw.length) return
  
  const existing = await getExisting(db, raw.map(r => r.id as string))
  
  const newProjects: ProjectRecord[] = []
  const unchanged: { pid: string; pubId: string | null }[] = []
  const changed: ProjectRecord[] = []
  
  for (const r of raw) {
    const p = parseSearchResult(r)
    const k = key(p.simap_project_id, p.simap_publication_id)
    const ex = existing.get(k)
    
    if (!ex) {
      // NEU: Komplett neues Projekt
      newProjects.push(p)
      stats.new_projects++
    } else if (ex.hash !== p.content_hash) {
      // #8: Hash-Vergleich - Projekt hat sich geändert
      changed.push(p)
      stats.updated_projects++
    } else {
      // Keine Änderung - nur last_checked_at updaten
      unchanged.push({ pid: p.simap_project_id, pubId: p.simap_publication_id })
      stats.skipped_projects++
    }
  }
  
  console.log(`[HOURLY] ${stats.new_projects} new, ${stats.updated_projects} changed, ${stats.skipped_projects} unchanged`)
  
  // #5: Parallele Detail-Fetches für NEUE Projekte
  if (!config.skipDetails && newProjects.length) {
    const projectsNeedingDetails = newProjects.filter(
      p => PUB_TYPES_WITH_DETAILS.includes(p.pub_type) && p.simap_publication_id
    )
    
    console.log(`[HOURLY] Fetching details for ${projectsNeedingDetails.length} new projects (${DETAIL_CONCURRENCY} parallel)...`)
    
    // Parallele Verarbeitung mit Concurrency-Limit
    let completed = 0
    for (let i = 0; i < projectsNeedingDetails.length; i += DETAIL_CONCURRENCY) {
      const batch = projectsNeedingDetails.slice(i, i + DETAIL_CONCURRENCY)
      
      await Promise.all(batch.map(async (p) => {
        const result = await fetchDetail(p.simap_project_id, p.simap_publication_id!)
        
        if (result.success && result.data) {
          enrichWithDetail(p, result.data)
          stats.details_fetched++
        } else if (result.error?.type === 'not_found') {
          stats.details_not_found++
        } else {
          stats.details_errors++
          if (result.error?.retryable) {
            console.warn(`[RETRY] ${p.simap_project_id}: ${result.error.message}`)
          }
        }
        
        completed++
      }))
      
      // Rate limiting zwischen Batches
      if (i + DETAIL_CONCURRENCY < projectsNeedingDetails.length) {
        await delay(DELAY_DETAIL_MS)
      }
    }
    
    // Skipped zählen (Projekte ohne Details-Typ)
    stats.details_skipped = newProjects.length - projectsNeedingDetails.length
  }
  
  // Insert neue Projekte
  if (newProjects.length) await upsertProjects(db, newProjects)
  
  // Update geänderte Projekte
  if (changed.length) await upsertProjects(db, changed)
  
  // #4: Batch-Update für last_checked_at
  if (unchanged.length) await updateLastChecked(db, unchanged)
}

async function syncRefresh(db: SupabaseClient, config: SyncConfig, stats: SyncStats): Promise<void> {
  console.log(`[REFRESH] Finding projects with details older than ${config.detailMaxAgeHours}h (${(config.detailMaxAgeHours/24).toFixed(1)} days)`)
  
  // Zähle wie viele Projekte insgesamt in der Queue sind
  const cutoff = new Date()
  cutoff.setHours(cutoff.getHours() - config.detailMaxAgeHours)
  
  const { count: totalInQueue } = await db.from('projects')
    .select('*', { count: 'exact', head: true })
    .in('pub_type', PUB_TYPES_WITH_DETAILS)
    .or(`detail_fetched_at.is.null,detail_fetched_at.lt.${cutoff.toISOString()}`)
  
  const projects = await getProjectsNeedingDetails(db, config.detailMaxAgeHours, config.refreshLimit)
  stats.fetched = projects.length
  
  if (!projects.length) {
    console.log('[REFRESH] All details are fresh ✓')
    return
  }
  
  const remainingAfter = (totalInQueue || 0) - projects.length
  console.log(`[REFRESH] Queue: ${totalInQueue} total, processing ${projects.length}, ~${remainingAfter} remaining`)
  console.log(`[REFRESH] Refreshing ${projects.length} projects (${DETAIL_CONCURRENCY} parallel)...`)
  
  // #5: Parallele Verarbeitung
  const projectsWithPubId = projects.filter(p => p.simap_publication_id !== null)
  
  for (let i = 0; i < projectsWithPubId.length; i += DETAIL_CONCURRENCY) {
    const batch = projectsWithPubId.slice(i, i + DETAIL_CONCURRENCY)
    
    await Promise.all(batch.map(async ({ simap_project_id, simap_publication_id, pub_type }) => {
      const result = await fetchDetail(simap_project_id, simap_publication_id!)
      
      if (result.success && result.data) {
        // Minimales ProjectRecord für Detail-Update
        const p = {
          simap_project_id,
          simap_publication_id,
          pub_type,
          cpv_codes: [] as string[],
          bkp_codes: [] as string[],
          oag_codes: [] as string[],
        } as unknown as ProjectRecord
        
        enrichWithDetail(p, result.data)
        await updateDetails(db, p)
        stats.details_fetched++
        stats.updated_projects++
      } else if (result.error?.type === 'not_found') {
        // 404 = Publikation existiert nicht mehr
        // Markiere als "versucht" um Projekt aus der Queue zu entfernen
        // Verhindert "Stuck-in-the-Past" Problem
        await markDetailAttempted(db, simap_project_id, simap_publication_id)
        stats.details_not_found++
      } else {
        // Temporäre Fehler (5xx, network) = NICHT markieren, wird später erneut versucht
        stats.details_errors++
      }
    }))
    
    if (i + DETAIL_CONCURRENCY < projectsWithPubId.length) {
      await delay(DELAY_DETAIL_MS)
    }
  }
  
  stats.details_skipped = projects.length - projectsWithPubId.length
}

async function syncFull(db: SupabaseClient, config: SyncConfig, stats: SyncStats): Promise<void> {
  const start = new Date()
  start.setDate(start.getDate() - config.daysBack)
  const startStr = start.toISOString().split('T')[0]
  
  console.log(`[FULL] Since ${startStr}`)
  
  const raw = await searchProjects(startStr, config.cantons)
  stats.fetched = raw.length
  if (!raw.length) return
  
  const existing = await getExisting(db, raw.map(r => r.id as string))
  const projects: ProjectRecord[] = []
  const needsDetail: ProjectRecord[] = []
  
  for (const r of raw) {
    const p = parseSearchResult(r)
    const k = key(p.simap_project_id, p.simap_publication_id)
    const ex = existing.get(k)
    
    projects.push(p)
    
    if (!ex) {
      stats.new_projects++
      if (PUB_TYPES_WITH_DETAILS.includes(p.pub_type) && p.simap_publication_id) {
        needsDetail.push(p)
      }
    } else {
      stats.updated_projects++
      // Re-fetch details if missing
      if (!ex.detailAt && PUB_TYPES_WITH_DETAILS.includes(p.pub_type) && p.simap_publication_id) {
        needsDetail.push(p)
      }
    }
  }
  
  console.log(`[FULL] ${stats.new_projects} new, ${stats.updated_projects} existing, ${needsDetail.length} need details`)
  
  // #5: Parallele Detail-Fetches
  if (!config.skipDetails && needsDetail.length) {
    console.log(`[FULL] Fetching details (${DETAIL_CONCURRENCY} parallel)...`)
    
    for (let i = 0; i < needsDetail.length; i += DETAIL_CONCURRENCY) {
      const batch = needsDetail.slice(i, i + DETAIL_CONCURRENCY)
      
      await Promise.all(batch.map(async (p) => {
        const result = await fetchDetail(p.simap_project_id, p.simap_publication_id!)
        
        if (result.success && result.data) {
          enrichWithDetail(p, result.data)
          stats.details_fetched++
        } else if (result.error?.type === 'not_found') {
          stats.details_not_found++
        } else {
          stats.details_errors++
        }
      }))
      
      if (i + DETAIL_CONCURRENCY < needsDetail.length) {
        await delay(DELAY_DETAIL_MS)
      }
    }
  }
  
  await upsertProjects(db, projects)
}

// ============================================================================
// MAIN
// ============================================================================

serve(async (req) => {
  const t0 = Date.now()
  const stats: SyncStats = {
    mode: 'hourly',
    fetched: 0,
    new_projects: 0,
    updated_projects: 0,
    skipped_projects: 0,
    details_fetched: 0,
    details_skipped: 0,
    details_errors: 0,
    details_not_found: 0,
    duration_seconds: 0,
  }
  
  try {
    const db = createClient(Deno.env.get('SUPABASE_URL')!, Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!)
    const url = new URL(req.url)
    
    const config: SyncConfig = {
      mode: (url.searchParams.get('mode') || 'hourly') as SyncMode,
      hoursBack: parseInt(url.searchParams.get('hours_back') || '3'),
      daysBack: parseInt(url.searchParams.get('days_back') || '30'),
      // WICHTIG: refresh_limit und detail_max_age_hours müssen zusammenpassen!
      // Default: 750 Projekte × 6 Aufrufe/Tag × 7 Tage = 31.500 Kapazität
      refreshLimit: parseInt(url.searchParams.get('refresh_limit') || '750'),
      // Default: 168h = 7 Tage - alle Projekte werden 1x pro Woche aktualisiert
      detailMaxAgeHours: parseInt(url.searchParams.get('detail_max_age_hours') || '168'),
      cantons: url.searchParams.get('cantons')?.split(',') || DEFAULT_CANTONS,
      skipDetails: url.searchParams.get('skip_details') === 'true',
    }
    
    stats.mode = config.mode
    console.log(`━━━ SIMAP Sync v8 | ${config.mode.toUpperCase()} ━━━`)
    
    switch (config.mode) {
      case 'hourly': await syncHourly(db, config, stats); break
      case 'refresh': await syncRefresh(db, config, stats); break
      case 'full': await syncFull(db, config, stats); break
    }
    
    stats.duration_seconds = (Date.now() - t0) / 1000
    console.log(`✓ ${stats.new_projects} new, ${stats.updated_projects} updated, ${stats.details_fetched} details, ${stats.details_not_found} not found (${stats.duration_seconds.toFixed(1)}s)`)
    
    return new Response(JSON.stringify({ success: true, stats }), {
      headers: { 'Content-Type': 'application/json' }
    })
  } catch (e) {
    stats.duration_seconds = (Date.now() - t0) / 1000
    console.error(`[ERROR] ${(e as Error).message}`)
    return new Response(JSON.stringify({ success: false, error: (e as Error).message, stats }), {
      headers: { 'Content-Type': 'application/json' }, status: 500
    })
  }
})
