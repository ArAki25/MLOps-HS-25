// ============================================================================
// Supabase Edge Function: SIMAP Sync v3
// ============================================================================
// Strategie: Search-API für Liste, Detail-API für ALLE relevanten Projekte
//
// Workflow:
// 1. Search-API → Alle Projekte in Zeitraum
// 2. Detail-API → Für JEDEN Tender/Award Details holen
// 3. Upsert → Alles in DB speichern
//
// Verwendung:
// - POST /functions/v1/SIMAP-Sync
// - POST /functions/v1/SIMAP-Sync?days_back=7
// - POST /functions/v1/SIMAP-Sync?full_sync=true
// - POST /functions/v1/SIMAP-Sync?skip_details=true (nur für Testing)
// - POST /functions/v1/SIMAP-Sync?refetch_details=true (Details neu holen)
// ============================================================================

import { serve } from "https://deno.land/std@0.168.0/http/server.ts"
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

// ============================================================================
// KONFIGURATION
// ============================================================================

const SIMAP_API_BASE = "https://www.simap.ch/api"
const SEARCH_ENDPOINT = "/publications/v2/project/project-search"
const DETAIL_ENDPOINT = "/publications/v1/project"

// Rate limiting - SIMAP mag keine zu schnellen Requests
const DELAY_BETWEEN_REQUESTS_MS = 150
const DELAY_BETWEEN_DETAIL_CALLS_MS = 200

// Standard-Kantone (Deutschschweiz)
const DEFAULT_CANTONS = [
  "ZH", "BE", "LU", "UR", "SZ", "OW", "NW", "GL", "ZG",
  "SO", "BS", "BL", "SH", "AR", "AI", "SG", "GR", "AG", "TG",
]

// Pub-Types für die wir Details holen (alle relevanten)
const PUB_TYPES_WITH_DETAILS = [
  'tender', 
  'award', 
  'direct_award',
  'competition', 
  'study_contract',
  'participant_selection',
  'selective_offering_phase',
]

// ============================================================================
// TYPES
// ============================================================================

interface SyncStats {
  fetched: number
  new_projects: number
  updated_projects: number
  details_fetched: number
  details_skipped: number
  details_errors: number
  duration_seconds: number
}

interface ParsedProject {
  simap_project_id: string
  simap_publication_id: string
  project_number: string | null
  publication_number: string | null
  title_de: string | null
  title_fr: string | null
  title_it: string | null
  title_en: string | null
  description_de: string | null
  description_fr: string | null
  description_it: string | null
  description_en: string | null
  publication_date: string
  proc_office_name_de: string | null
  proc_office_name_fr: string | null
  proc_office_id: string | null
  canton: string | null
  city: string | null
  postal_code: string | null
  country: string
  pub_type: string
  project_type: string | null
  project_subtype: string | null
  process_type: string | null
  order_type: string | null
  lots_type: string | null
  corrected: boolean
  cpv_code_main: string | null
  cpv_codes: string[]
  bkp_codes: string[]
  ebkph_codes: string[]
  ebkpt_codes: string[]
  npk_codes: string[]
  oag_codes: string[]
  estimated_value: number | null
  estimated_value_currency: string | null
  submission_deadline: string | null
  offer_opening_date: string | null
  execution_start: string | null
  execution_end: string | null
  winner_name: string | null
  winner_city: string | null
  winner_canton: string | null
  award_amount: number | null
  award_currency: string | null
  award_vat_type: string | null
  number_of_submissions: number | null
  award_decision_date: string | null
  lots_count: number
  raw_json_search: any
  raw_json_detail: any | null
  detail_fetched_at: string | null
  detail_fetch_error: string | null
}

// ============================================================================
// PARSING HELPERS
// ============================================================================

function parseTranslation(obj: any): { de?: string; fr?: string; it?: string; en?: string } {
  if (!obj || typeof obj !== 'object') return {}
  return {
    de: obj.de || null,
    fr: obj.fr || null,
    it: obj.it || null,
    en: obj.en || null,
  }
}

function parseOrderAddress(obj: any): {
  canton: string | null
  city: string | null
  postal_code: string | null
  country: string
} {
  if (!obj || typeof obj !== 'object') {
    return { canton: null, city: null, postal_code: null, country: 'CH' }
  }
  
  let city: string | null = null
  const cityObj = obj.city
  if (typeof cityObj === 'string') {
    city = cityObj
  } else if (cityObj && typeof cityObj === 'object') {
    city = cityObj.de || cityObj.fr || cityObj.it || cityObj.en || null
  }
  
  return {
    canton: obj.cantonId || obj.canton || null,
    city: city,
    postal_code: obj.postalCode || null,
    country: obj.countryId || obj.country || 'CH',
  }
}

function parseDate(dateStr: string | undefined | null): string | null {
  if (!dateStr) return null
  try {
    if (dateStr.includes('T')) return dateStr.split('T')[0]
    if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) return dateStr
    const date = new Date(dateStr)
    if (!isNaN(date.getTime())) return date.toISOString().split('T')[0]
  } catch { }
  return null
}

function parseDateTime(dateStr: string | undefined | null): string | null {
  if (!dateStr) return null
  try {
    const date = new Date(dateStr)
    if (!isNaN(date.getTime())) return date.toISOString()
  } catch { }
  return null
}

function extractCpvCode(code: any): string | null {
  if (!code) return null
  if (typeof code === 'string') return code
  if (typeof code === 'object' && code.code) return code.code
  return null
}

function parseCodesArray(arr: any[] | undefined, extractor: (item: any) => string | null): string[] {
  if (!Array.isArray(arr)) return []
  return arr.map(extractor).filter((c): c is string => c !== null)
}

// ============================================================================
// SEARCH API PARSING
// ============================================================================

function parseSearchEntry(entry: any): ParsedProject {
  const title = parseTranslation(entry.title)
  const procOfficeName = parseTranslation(entry.procOfficeName)
  let orderAddress = parseOrderAddress(entry.orderAddress)
  
  // Falls keine Adresse, aus erstem Lot nehmen
  if (!orderAddress.canton && entry.lots && entry.lots.length > 0) {
    orderAddress = parseOrderAddress(entry.lots[0].orderAddress)
  }
  
  // Publication number kann nested sein
  let publicationNumber: string | null = null
  if (typeof entry.publicationNumber === 'string') {
    publicationNumber = entry.publicationNumber
  } else if (entry.publicationNumber?.publicationNumber) {
    publicationNumber = entry.publicationNumber.publicationNumber
  }
  
  const pubDate = parseDate(entry.publicationDate) || new Date().toISOString().split('T')[0]
  
  return {
    simap_project_id: entry.id,
    simap_publication_id: entry.publicationId || null,
    project_number: entry.projectNumber || null,
    publication_number: publicationNumber,
    title_de: title.de || null,
    title_fr: title.fr || null,
    title_it: title.it || null,
    title_en: title.en || null,
    description_de: null, // Wird von Detail-API gefüllt
    description_fr: null,
    description_it: null,
    description_en: null,
    publication_date: pubDate,
    proc_office_name_de: procOfficeName.de || null,
    proc_office_name_fr: procOfficeName.fr || null,
    proc_office_id: entry.procOfficeId || null,
    canton: orderAddress.canton,
    city: orderAddress.city,
    postal_code: orderAddress.postal_code,
    country: orderAddress.country,
    pub_type: entry.pubType || 'unknown',
    project_type: entry.projectType || null,
    project_subtype: entry.projectSubType || null,
    process_type: entry.processType || null,
    order_type: entry.orderType || null,
    lots_type: entry.lotsType || null,
    corrected: entry.corrected || false,
    cpv_code_main: null, // Wird von Detail-API gefüllt
    cpv_codes: [],
    bkp_codes: [],
    ebkph_codes: [],
    ebkpt_codes: [],
    npk_codes: [],
    oag_codes: [],
    estimated_value: null,
    estimated_value_currency: null,
    submission_deadline: null,
    offer_opening_date: null,
    execution_start: null,
    execution_end: null,
    winner_name: null,
    winner_city: null,
    winner_canton: null,
    award_amount: null,
    award_currency: null,
    award_vat_type: null,
    number_of_submissions: null,
    award_decision_date: null,
    lots_count: entry.lots?.length || 0,
    raw_json_search: entry,
    raw_json_detail: null,
    detail_fetched_at: null,
    detail_fetch_error: null,
  }
}

// ============================================================================
// DETAIL API PARSING - DAS WICHTIGE!
// ============================================================================

function enrichWithDetail(project: ParsedProject, detail: any): ParsedProject {
  if (!detail) return project
  
  const now = new Date().toISOString()
  
  // Beschreibung aus procurement.orderDescription
  const orderDesc = parseTranslation(detail.procurement?.orderDescription)
  project.description_de = orderDesc.de || project.description_de
  project.description_fr = orderDesc.fr || project.description_fr
  project.description_it = orderDesc.it || project.description_it
  project.description_en = orderDesc.en || project.description_en
  
  // CPV-Codes aus procurement
  const mainCpv = extractCpvCode(detail.procurement?.cpvCode)
  if (mainCpv) {
    project.cpv_code_main = mainCpv
    project.cpv_codes = [mainCpv]
  }
  
  // Zusätzliche CPV-Codes
  const additionalCpv = parseCodesArray(
    detail.procurement?.additionalCpvCodes, 
    extractCpvCode
  )
  project.cpv_codes = [...new Set([...project.cpv_codes, ...additionalCpv])]
  
  // BKP-Codes
  project.bkp_codes = parseCodesArray(
    detail.procurement?.bkpCodes,
    (c) => typeof c === 'string' ? c : c?.code || null
  )
  
  // Weitere Codes
  project.ebkph_codes = parseCodesArray(
    detail.procurement?.ebkphCodes,
    (c) => typeof c === 'string' ? c : c?.code || null
  )
  project.ebkpt_codes = parseCodesArray(
    detail.procurement?.ebkptCodes,
    (c) => typeof c === 'string' ? c : c?.code || null
  )
  project.npk_codes = parseCodesArray(
    detail.procurement?.npkCodes,
    (c) => typeof c === 'string' ? c : c?.code || null
  )
  project.oag_codes = parseCodesArray(
    detail.procurement?.oagCodes,
    (c) => typeof c === 'string' ? c : c?.code || null
  )
  
  // Codes auch aus Lots sammeln
  if (detail.lots && Array.isArray(detail.lots)) {
    for (const lot of detail.lots) {
      // CPV aus Lot
      const lotCpv = extractCpvCode(lot.cpvCode)
      if (lotCpv && !project.cpv_codes.includes(lotCpv)) {
        project.cpv_codes.push(lotCpv)
      }
      const lotAdditionalCpv = parseCodesArray(lot.additionalCpvCodes, extractCpvCode)
      for (const c of lotAdditionalCpv) {
        if (!project.cpv_codes.includes(c)) project.cpv_codes.push(c)
      }
      
      // BKP aus Lot
      const lotBkp = parseCodesArray(lot.bkpCodes, (c) => typeof c === 'string' ? c : c?.code || null)
      for (const c of lotBkp) {
        if (!project.bkp_codes.includes(c)) project.bkp_codes.push(c)
      }
    }
  }
  
  // Geschätzter Wert
  if (detail.procurement?.estimatedValue) {
    project.estimated_value = detail.procurement.estimatedValue.amount || null
    project.estimated_value_currency = detail.procurement.estimatedValue.currency || 'CHF'
  }
  
  // Order Type (kann auch hier drin sein)
  if (detail.procurement?.orderType && !project.order_type) {
    project.order_type = detail.procurement.orderType
  }
  
  // Fristen aus dates
  if (detail.dates) {
    project.submission_deadline = parseDateTime(detail.dates.submissionDeadline)
    project.offer_opening_date = parseDateTime(detail.dates.offerOpeningDate)
    project.execution_start = parseDate(detail.dates.executionStart)
    project.execution_end = parseDate(detail.dates.executionEnd)
  }
  
  // Award-spezifische Daten
  if (project.pub_type === 'award' || project.pub_type === 'direct_award') {
    // Winner aus decision.vendors[0] (nicht award.winners!)
    if (detail?.decision?.vendors && detail.decision.vendors.length > 0) {
      const winner = detail.decision.vendors[0]
      project.winner_name = winner.vendorName || null
      
      const winnerAddr = winner.vendorAddress
      if (winnerAddr) {
        const winnerCity = winnerAddr.city
        if (typeof winnerCity === 'string') {
          project.winner_city = winnerCity
        } else if (winnerCity && typeof winnerCity === 'object') {
          project.winner_city = winnerCity.de || winnerCity.fr || winnerCity.it || null
        }
        project.winner_canton = winnerAddr.cantonId || winnerAddr.canton || null
      }
      
      // Award Amount aus decision.vendors[0].price.price
      if (winner.price?.price) {
        project.award_amount = typeof winner.price.price === 'number' 
          ? winner.price.price 
          : parseFloat(String(winner.price.price).replace(/'/g, '').replace(/,/g, ''))
        project.award_currency = winner.price.currency?.toUpperCase() || 'CHF'
        project.award_vat_type = winner.price.vatType || null
      }
    }
    
    // Fallback: Alte Struktur für Kompatibilität (falls vorhanden)
    const award = detail.award || detail
    if (!project.winner_name && award?.winners && award.winners.length > 0) {
      const winner = award.winners[0]
      project.winner_name = winner.vendorName || null
      
      const winnerAddr = winner.vendorAddress
      if (winnerAddr) {
        const winnerCity = winnerAddr.city
        if (typeof winnerCity === 'string') {
          project.winner_city = winnerCity
        } else if (winnerCity && typeof winnerCity === 'object') {
          project.winner_city = winnerCity.de || winnerCity.fr || winnerCity.it || null
        }
        project.winner_canton = winnerAddr.cantonId || winnerAddr.canton || null
      }
    }
    
    // Award Amount Fallback (falls nicht schon gesetzt)
    if (!project.award_amount) {
      let awardAmount = award?.awardPrice?.amount ?? 
                        award?.awardAmount ?? 
                        award?.awardPrice ?? 
                        null
      
      if (awardAmount) {
        if (typeof awardAmount === 'string') {
          awardAmount = parseFloat(awardAmount.replace(/'/g, '').replace(/,/g, ''))
        }
        project.award_amount = awardAmount
        project.award_currency = award?.awardPrice?.currency || 'CHF'
        project.award_vat_type = award?.awardPrice?.vatType || null
      }
    }
    
    project.number_of_submissions = award?.numberOfOffers ?? 
                                    award?.numberOfSubmissions ?? 
                                    null
    project.award_decision_date = parseDate(award?.awardDecisionDate)
  }
  
  // Raw Detail speichern
  project.raw_json_detail = detail
  project.detail_fetched_at = now
  project.detail_fetch_error = null
  
  return project
}

// ============================================================================
// API CALLS
// ============================================================================

async function fetchProjectsFromSearch(
  startDate: string,
  cantons: string[] | null,
  maxPages: number | null = null
): Promise<any[]> {
  const projects: any[] = []
  let lastItem: string | null = null
  let page = 0
  
  while (true) {
    const params = new URLSearchParams({ newestPublicationFrom: startDate })
    if (cantons && cantons.length > 0) {
      params.append('orderAddressCantons', cantons.join(','))
    }
    if (lastItem) params.set('lastItem', lastItem)
    
    const url = `${SIMAP_API_BASE}${SEARCH_ENDPOINT}?${params}`
    
    const response = await fetch(url, { headers: { 'Accept': 'application/json' } })
    if (!response.ok) {
      throw new Error(`SIMAP Search API Error: ${response.status}`)
    }
    
    const data = await response.json()
    const pageProjects = data.projects || []
    
    if (pageProjects.length === 0) break
    
    projects.push(...pageProjects)
    lastItem = data.pagination?.lastItem || null
    if (!lastItem) break
    
    page++
    if (maxPages && page >= maxPages) break
    
    await new Promise(resolve => setTimeout(resolve, DELAY_BETWEEN_REQUESTS_MS))
  }
  
  console.log(`[SEARCH] ${projects.length} Projekte von ${page + 1} Seiten geladen`)
  return projects
}

async function fetchProjectDetail(projectId: string, publicationId: string): Promise<any | null> {
  const url = `${SIMAP_API_BASE}${DETAIL_ENDPOINT}/${projectId}/publication-details/${publicationId}`
  
  try {
    const response = await fetch(url, { headers: { 'Accept': 'application/json' } })
    
    if (!response.ok) {
      if (response.status === 404 || response.status === 401 || response.status === 403) {
        return null // Kein Zugriff, nicht kritisch
      }
      throw new Error(`Detail API Error: ${response.status}`)
    }
    
    return await response.json()
  } catch (error) {
    console.warn(`[DETAIL] Fehler für ${projectId.slice(0, 8)}:`, (error as Error).message)
    return null
  }
}

// ============================================================================
// DATABASE HELPERS
// ============================================================================

function createProjectKey(projectId: string, publicationId: string | null | undefined): string {
  // Normalize null/undefined to null, then convert to string for key
  const pubId = publicationId ?? null
  return `${projectId}:${pubId === null ? 'null' : pubId}`
}

async function getLastPublicationDate(supabase: any): Promise<string | null> {
  const { data, error } = await supabase
    .from('projects')
    .select('publication_date')
    .order('publication_date', { ascending: false })
    .limit(1)
    .single()
  
  if (error || !data) return null
  return data.publication_date
}

function determineStartDate(daysBack: number | null, fullSync: boolean, lastDate: string | null): string {
  const today = new Date()
  
  if (daysBack !== null) {
    const date = new Date(today)
    date.setDate(date.getDate() - daysBack)
    return date.toISOString().split('T')[0]
  }
  
  if (fullSync) {
    const date = new Date(today)
    date.setDate(date.getDate() - 30)
    return date.toISOString().split('T')[0]
  }
  
  if (lastDate) {
    const date = new Date(lastDate)
    date.setDate(date.getDate() - 1) // Sicherheitspuffer
    return date.toISOString().split('T')[0]
  }
  
  const date = new Date(today)
  date.setDate(date.getDate() - 7)
  return date.toISOString().split('T')[0]
}

async function getExistingProjectIds(supabase: any, projectIds: string[]): Promise<Map<string, { hasDetail: boolean }>> {
  const existing = new Map<string, { hasDetail: boolean }>()
  const batchSize = 500
  
  for (let i = 0; i < projectIds.length; i += batchSize) {
    const batch = projectIds.slice(i, i + batchSize)
    const { data, error } = await supabase
      .from('projects')
      .select('simap_project_id, simap_publication_id, detail_fetched_at')
      .in('simap_project_id', batch)
    
    if (error) {
      console.warn(`[DEBUG] Query error for batch:`, error.message)
    }
    
    if (data) {
      for (const row of data) {
        const key = createProjectKey(row.simap_project_id, row.simap_publication_id)
        existing.set(key, { hasDetail: row.detail_fetched_at !== null })
      }
    }
  }
  
  return existing
}

// ============================================================================
// MAIN SYNC LOGIC
// ============================================================================

serve(async (req) => {
  const startTime = Date.now()
  const stats: SyncStats = {
    fetched: 0,
    new_projects: 0,
    updated_projects: 0,
    details_fetched: 0,
    details_skipped: 0,
    details_errors: 0,
    duration_seconds: 0,
  }
  
  try {
    const supabaseUrl = Deno.env.get('SUPABASE_URL')!
    const supabaseKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
    const supabase = createClient(supabaseUrl, supabaseKey)
    
    // Parse parameters
    const url = new URL(req.url)
    const daysBackParam = url.searchParams.get('days_back')
    const daysBack = daysBackParam ? parseInt(daysBackParam) : null
    const fullSync = url.searchParams.get('full_sync') === 'true'
    const cantonsParam = url.searchParams.get('cantons')
    const cantons = cantonsParam ? cantonsParam.split(',') : DEFAULT_CANTONS
    const maxPagesParam = url.searchParams.get('max_pages')
    const maxPages = maxPagesParam ? parseInt(maxPagesParam) : null
    const skipDetails = url.searchParams.get('skip_details') === 'true'
    const refetchDetails = url.searchParams.get('refetch_details') === 'true'
    
    console.log(`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`)
    console.log(`[SYNC START] v3`)
    console.log(`  days_back=${daysBack}, full_sync=${fullSync}`)
    console.log(`  skip_details=${skipDetails}, refetch_details=${refetchDetails}`)
    console.log(`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`)
    
    // Determine start date
    const lastDate = await getLastPublicationDate(supabase)
    const startDate = determineStartDate(daysBack, fullSync, lastDate)
    console.log(`[CONFIG] Start: ${startDate}, Last in DB: ${lastDate || 'none'}`)
    
    // ========== PHASE 1: SEARCH API ==========
    console.log(`[PHASE 1] Fetching from Search API...`)
    const rawProjects = await fetchProjectsFromSearch(startDate, cantons, maxPages)
    stats.fetched = rawProjects.length
    
    if (rawProjects.length === 0) {
      stats.duration_seconds = (Date.now() - startTime) / 1000
      return new Response(
        JSON.stringify({ success: true, message: 'No projects found', stats }),
        { headers: { 'Content-Type': 'application/json' } }
      )
    }
    
    // Check which projects exist and have details
    const projectIds = rawProjects.map(p => p.id)
    const existingMap = await getExistingProjectIds(supabase, projectIds)
    console.log(`[DEBUG] Found ${existingMap.size} existing projects in DB`)
    
    // Parse all projects
    const projects: ParsedProject[] = rawProjects.map(parseSearchEntry)
    
    // Categorize: new vs existing
    const newProjects: ParsedProject[] = []
    const existingProjects: ParsedProject[] = []
    const needsDetail: ParsedProject[] = []
    
    // Debug: Sample some keys to see what we're comparing
    if (projects.length > 0) {
      const sample = projects.slice(0, 3)
      console.log(`[DEBUG] Sample project keys:`)
      for (const p of sample) {
        const key = createProjectKey(p.simap_project_id, p.simap_publication_id)
        const exists = existingMap.has(key)
        console.log(`  ${key} -> exists: ${exists}, pub_id: ${p.simap_publication_id}`)
      }
    }
    
    for (const project of projects) {
      const key = createProjectKey(project.simap_project_id, project.simap_publication_id)
      const existing = existingMap.get(key)
      
      if (!existing) {
        newProjects.push(project)
        // Neue Projekte brauchen Details
        if (PUB_TYPES_WITH_DETAILS.includes(project.pub_type)) {
          needsDetail.push(project)
        }
      } else {
        existingProjects.push(project)
        // Bestehende nur wenn refetch oder noch keine Details
        if (refetchDetails || !existing.hasDetail) {
          if (PUB_TYPES_WITH_DETAILS.includes(project.pub_type)) {
            needsDetail.push(project)
          }
        }
      }
    }
    
    stats.new_projects = newProjects.length
    stats.updated_projects = existingProjects.length
    console.log(`[PHASE 1] ${newProjects.length} new, ${existingProjects.length} existing`)
    console.log(`[PHASE 1] ${needsDetail.length} need details`)
    
    // ========== PHASE 2: DETAIL API ==========
    if (!skipDetails && needsDetail.length > 0) {
      console.log(`[PHASE 2] Fetching details for ${needsDetail.length} projects...`)
      
      let detailCount = 0
      for (const project of needsDetail) {
        try {
          const detail = await fetchProjectDetail(
            project.simap_project_id, 
            project.simap_publication_id
          )
          
          if (detail) {
            enrichWithDetail(project, detail)
            stats.details_fetched++
            detailCount++
            
            if (detailCount % 10 === 0) {
              console.log(`[PHASE 2] ${detailCount}/${needsDetail.length} details fetched`)
            }
          } else {
            stats.details_skipped++
            project.detail_fetch_error = 'Not found or no access'
          }
          
          // Rate limit
          await new Promise(resolve => setTimeout(resolve, DELAY_BETWEEN_DETAIL_CALLS_MS))
          
        } catch (error) {
          stats.details_errors++
          project.detail_fetch_error = (error as Error).message
        }
      }
      
      console.log(`[PHASE 2] Done: ${stats.details_fetched} fetched, ${stats.details_skipped} skipped, ${stats.details_errors} errors`)
    } else if (skipDetails) {
      console.log(`[PHASE 2] Skipped (skip_details=true)`)
    }
    
    // ========== PHASE 3: UPSERT ==========
    console.log(`[PHASE 3] Upserting to database...`)
    console.log(`[DEBUG] Upserting ${projects.length} projects (${newProjects.length} new, ${existingProjects.length} existing)`)
    const batchSize = 200
    
    let upsertedCount = 0
    for (let i = 0; i < projects.length; i += batchSize) {
      const batch = projects.slice(i, i + batchSize)
      const batchNum = Math.floor(i/batchSize) + 1
      
      // Debug: Show sample of what we're upserting
      if (batchNum === 1 && batch.length > 0) {
        const sample = batch[0]
        console.log(`[DEBUG] Sample upsert: project_id=${sample.simap_project_id}, publication_id=${sample.simap_publication_id ?? 'null'}`)
      }
      
      const { data, error } = await supabase
        .from('projects')
        .upsert(batch, { 
          onConflict: 'simap_project_id,simap_publication_id',
          ignoreDuplicates: false
        })
        .select('simap_project_id')
      
      if (error) {
        console.error(`[ERROR] Batch ${batchNum} failed:`, error.message)
        throw error
      }
      
      if (data) {
        upsertedCount += data.length
      } else {
        upsertedCount += batch.length // Fallback: assume all were upserted
      }
    }
    
    console.log(`[PHASE 3] Upserted ${upsertedCount} projects`)
    
    stats.duration_seconds = (Date.now() - startTime) / 1000
    
    // Summary
    console.log(`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`)
    console.log(`✓ SYNC COMPLETED`)
    console.log(`  Fetched:      ${stats.fetched}`)
    console.log(`  New:          ${stats.new_projects}`)
    console.log(`  Updated:      ${stats.updated_projects}`)
    console.log(`  Details:      ${stats.details_fetched}`)
    console.log(`  Duration:     ${stats.duration_seconds.toFixed(2)}s`)
    console.log(`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`)
    
    return new Response(
      JSON.stringify({
        success: true,
        message: `Sync: ${stats.new_projects} new, ${stats.updated_projects} updated, ${stats.details_fetched} enriched`,
        stats,
      }),
      { headers: { 'Content-Type': 'application/json' }, status: 200 }
    )
    
  } catch (error) {
    stats.duration_seconds = (Date.now() - startTime) / 1000
    console.error(`[SYNC FAILED] ${(error as Error).message}`)
    
    return new Response(
      JSON.stringify({ success: false, error: (error as Error).message, stats }),
      { headers: { 'Content-Type': 'application/json' }, status: 500 }
    )
  }
})
