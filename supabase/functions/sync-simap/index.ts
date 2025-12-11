// Supabase Edge Function: SIMAP Sync
// Synchronisiert SIMAP-Projekte in die Supabase Datenbank
//
// Verwendung:
// - Manuell: POST https://dein-project.supabase.co/functions/v1/sync-simap
// - Als Cron: Via pg_cron (siehe setup.sql)

import { serve } from "https://deno.land/std@0.168.0/http/server.ts"
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const SIMAP_API_BASE = "https://www.simap.ch/api"
const SEARCH_ENDPOINT = "/publications/v2/project/project-search"

// Standard-Kantone (Deutschschweiz)
const DEFAULT_CANTONS = [
  "ZH", "BE", "LU", "UR", "SZ", "OW", "NW", "GL", "ZG",
  "SO", "BS", "BL", "SH", "AR", "AI", "SG", "GR", "AG", "TG",
]

interface ProjectEntry {
  id: string
  publicationId: string
  projectNumber?: string
  publicationNumber?: { publicationNumber?: string }
  title?: { de?: string; fr?: string; it?: string; en?: string }
  publicationDate: string
  pubType: string
  projectType?: string
  projectSubType?: string
  processType?: string
  orderType?: string
  lotsType?: string
  corrected?: boolean
  procOfficeName?: { de?: string; fr?: string; it?: string; en?: string }
  orderAddress?: {
    canton?: string
    city?: string | { de?: string; fr?: string; it?: string }
    postalCode?: string
    country?: string
  }
  lots?: Array<{ orderAddress?: any }>
  cpvCodes?: string[]
  bkpCodes?: string[]
}

interface SyncStats {
  fetched: number
  inserted: number
  updated: number
  errors: number
  duration_seconds: number
}

function parseTranslation(obj: any): { de?: string; fr?: string; it?: string } {
  if (!obj || typeof obj !== 'object') return {}
  return {
    de: obj.de || null,
    fr: obj.fr || null,
    it: obj.it || null,
  }
}

function parseOrderAddress(obj: any): {
  canton?: string
  city?: string
  postal_code?: string
  country?: string
} {
  if (!obj || typeof obj !== 'object') return {}
  
  let city: string | null = null
  const cityObj = obj.city
  if (typeof cityObj === 'string') {
    city = cityObj
  } else if (cityObj && typeof cityObj === 'object') {
    city = cityObj.de || cityObj.fr || cityObj.it || null
  }
  
  return {
    canton: obj.canton || null,
    city: city,
    postal_code: obj.postalCode || null,
    country: obj.country || 'CH',
  }
}

function parseProjectEntry(entry: ProjectEntry): any {
  const title = parseTranslation(entry.title)
  const procOfficeName = parseTranslation(entry.procOfficeName)
  let orderAddress = parseOrderAddress(entry.orderAddress)
  
  // Falls keine Adresse, aus Lots nehmen
  if (!orderAddress.canton && entry.lots && entry.lots.length > 0) {
    orderAddress = parseOrderAddress(entry.lots[0].orderAddress)
  }
  
  const publicationNumber = entry.publicationNumber?.publicationNumber || null
  
  // Datum parsen
  const pubDate = entry.publicationDate ? entry.publicationDate.split('T')[0] : new Date().toISOString().split('T')[0]
  
  return {
    simap_project_id: entry.id,
    simap_publication_id: entry.publicationId,
    project_number: entry.projectNumber || null,
    publication_number: publicationNumber,
    title_de: title.de || null,
    title_fr: title.fr || null,
    title_it: title.it || null,
    publication_date: pubDate,
    pub_type: entry.pubType || 'unknown',
    project_type: entry.projectType || null,
    project_subtype: entry.projectSubType || null,
    process_type: entry.processType || null,
    order_type: entry.orderType || null,
    lots_type: entry.lotsType || null,
    corrected: entry.corrected || false,
    proc_office_name_de: procOfficeName.de || null,
    proc_office_name_fr: procOfficeName.fr || null,
    canton: orderAddress.canton || null,
    city: orderAddress.city || null,
    postal_code: orderAddress.postal_code || null,
    country: orderAddress.country || 'CH',
    cpv_codes: entry.cpvCodes || [],
    bkp_codes: entry.bkpCodes || [],
    lots_count: entry.lots?.length || 0,
    raw_json: entry,
  }
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

function determineStartDate(
  daysBack: number | null,
  fullSync: boolean,
  lastDate: string | null
): string {
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
  
  // Delta-Sync
  if (lastDate) {
    const date = new Date(lastDate)
    date.setDate(date.getDate() - 1) // Sicherheitspuffer
    return date.toISOString().split('T')[0]
  }
  
  // Keine Daten: 7 Tage zurück
  const date = new Date(today)
  date.setDate(date.getDate() - 7)
  return date.toISOString().split('T')[0]
}

async function fetchProjectsFromSimap(
  startDate: string,
  cantons: string[] | null,
  maxPages: number | null = null
): Promise<ProjectEntry[]> {
  const projects: ProjectEntry[] = []
  let lastItem: string | null = null
  let page = 0
  
  while (true) {
    const params = new URLSearchParams({
      newestPublicationFrom: startDate,
    })
    
    if (cantons && cantons.length > 0) {
      params.append('orderAddressCantons', cantons.join(','))
    }
    
    if (lastItem) {
      params.set('lastItem', lastItem)
    }
    
    const url = `${SIMAP_API_BASE}${SEARCH_ENDPOINT}?${params}`
    
    try {
      const response = await fetch(url, {
        headers: {
          'Accept': 'application/json',
        },
      })
      
      if (!response.ok) {
        throw new Error(`SIMAP API Error: ${response.status} ${response.statusText}`)
      }
      
      const data = await response.json()
      const pageProjects: ProjectEntry[] = data.projects || []
      
      if (pageProjects.length === 0) {
        break
      }
      
      projects.push(...pageProjects)
      
      lastItem = data.pagination?.lastItem || null
      if (!lastItem) {
        break
      }
      
      page++
      if (maxPages && page >= maxPages) {
        break
      }
      
      // Rate limiting
      await new Promise(resolve => setTimeout(resolve, 100))
      
    } catch (error) {
      console.error(`Error fetching page ${page + 1}:`, error)
      throw error
    }
  }
  
  return projects
}

serve(async (req) => {
  const startTime = Date.now()
  const stats: SyncStats = {
    fetched: 0,
    inserted: 0,
    updated: 0,
    errors: 0,
    duration_seconds: 0,
  }
  
  try {
    // Supabase Client
    const supabaseUrl = Deno.env.get('SUPABASE_URL')!
    const supabaseKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
    const supabase = createClient(supabaseUrl, supabaseKey)
    
    // Parameter aus Request
    const url = new URL(req.url)
    const daysBackParam = url.searchParams.get('days_back')
    const daysBack = daysBackParam ? parseInt(daysBackParam) : null
    const fullSync = url.searchParams.get('full_sync') === 'true'
    const cantonsParam = url.searchParams.get('cantons')
    const cantons = cantonsParam ? cantonsParam.split(',') : DEFAULT_CANTONS
    const maxPagesParam = url.searchParams.get('max_pages')
    const maxPages = maxPagesParam ? parseInt(maxPagesParam) : null
    
    console.log(`Starting sync: days_back=${daysBack}, full_sync=${fullSync}, cantons=${cantons.length}`)
    
    // Start-Datum bestimmen
    const lastDate = await getLastPublicationDate(supabase)
    const startDate = determineStartDate(daysBack, fullSync, lastDate)
    
    console.log(`Start date: ${startDate}, Last date in DB: ${lastDate || 'none'}`)
    
    // Projekte von SIMAP API holen
    const rawProjects = await fetchProjectsFromSimap(startDate, cantons, maxPages)
    stats.fetched = rawProjects.length
    
    console.log(`Fetched ${rawProjects.length} projects from SIMAP API`)
    
    if (rawProjects.length === 0) {
      stats.duration_seconds = (Date.now() - startTime) / 1000
      return new Response(
        JSON.stringify({
          success: true,
          message: 'No new projects found',
          stats,
        }),
        { headers: { 'Content-Type': 'application/json' } }
      )
    }
    
    // Projekte parsen und in DB einfügen (Batch)
    const batchSize = 500
    let totalInserted = 0
    
    for (let i = 0; i < rawProjects.length; i += batchSize) {
      const batch = rawProjects.slice(i, i + batchSize)
      const parsedProjects = batch.map(parseProjectEntry)
      
      const { data, error } = await supabase
        .from('projects')
        .upsert(parsedProjects, {
          onConflict: 'simap_project_id,simap_publication_id',
        })
        .select()
      
      if (error) {
        console.error(`Error upserting batch ${i / batchSize + 1}:`, error)
        stats.errors++
        throw error
      }
      
      totalInserted += parsedProjects.length
    }
    
    stats.inserted = totalInserted
    stats.duration_seconds = (Date.now() - startTime) / 1000
    
    console.log(`✓ Sync completed: ${stats.fetched} fetched, ${stats.inserted} inserted`)
    
    return new Response(
      JSON.stringify({
        success: true,
        message: 'Sync completed successfully',
        stats,
      }),
      {
        headers: { 'Content-Type': 'application/json' },
        status: 200,
      }
    )
    
  } catch (error) {
    stats.errors++
    stats.duration_seconds = (Date.now() - startTime) / 1000
    
    console.error('Sync error:', error)
    
    return new Response(
      JSON.stringify({
        success: false,
        error: error.message,
        stats,
      }),
      {
        headers: { 'Content-Type': 'application/json' },
        status: 500,
      }
    )
  }
})
