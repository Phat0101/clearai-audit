import { tool } from 'ai';
import { z } from 'zod';
import { tavily } from '@tavily/core';
import { toolResultSchema, ToolResult } from '@/types/search';
import { cleanupTariffData } from '@/lib/cleanData';

// Initialize Tavily client
const tvly = tavily({ apiKey: process.env.TAVILY_API_KEY! });

// Track searches to prevent duplicates
const searchCache = new Map();

/**
 * Australian tariff classification tools for AI chat
 */
export const auTariffTools = {
  tariff_chapter_lookup: tool({
    description: 'Look up all HS Codes that belong to your selected 4-digit chapter. Use ONLY AFTER stating your chapter selection.',
    inputSchema: z.object({
      hs_code: z.string().length(4).regex(/^\d+$/, 'Must be a 4-digit chapter code')
    }),
    execute: async ({ hs_code }) => {
      // Extract 2-digit chapter code for notes lookup
      const chapterCode = hs_code.slice(0, 2);
      
      console.log('🔍 API Calls:', {
        timestamp: new Date().toISOString(),
        tariffUrl: `https://api.clear.ai/api/v1/au_tariff/tariffs/chapter_flatten_tariffs?code=${hs_code}`,
        notesUrl: `https://api.clear.ai/api/v1/au_tariff/chapters/by_code?code=${chapterCode}`,
      });
      
      try {
        // Parallel API calls
        const [tariffResponse, notesResponse] = await Promise.all([
          fetch(`https://api.clear.ai/api/v1/au_tariff/tariffs/chapter_flatten_tariffs?code=${hs_code}`),
          fetch(`https://api.clear.ai/api/v1/au_tariff/chapters/by_code?code=${chapterCode}`)
        ]);
        
        console.log('📡 API Responses:', {
          timestamp: new Date().toISOString(),
          tariffStatus: tariffResponse.status,
          notesStatus: notesResponse.status
        });

        if (!tariffResponse.ok || !notesResponse.ok) {
          throw new Error(`API request failed: Tariffs (${tariffResponse.status}) or Notes (${notesResponse.status})`);
        }

        const [tariffData, notesData] = await Promise.all([
          tariffResponse.json(),
          notesResponse.json()
        ]);

        return JSON.stringify({
          content: 'Processing tariff data...',
          rawData: tariffData,
          chapterNotes: notesData,
          images: []
        });

      } catch (error) {
        console.error('❌ API Error:', {
          error,
          hs_code,
          timestamp: new Date().toISOString()
        });
        return JSON.stringify({
          content: 'Error occurred',
          rawData: [],
          chapterNotes: null,
          images: []
        });
      }
    }
  }),

  tariff_search: tool({
    description: 'Detailed lookup for specific HS codes (2-8 digits). Use ONLY when user provides specific HS codes to look up. Only run once at a time. You must search with at least 2 digits up to 8 digits.',
    inputSchema: z.object({
      hs_code: z.string()
        .regex(/^\d+$/, 'Must be numeric HS code')
        .min(2, 'Must be at least 2 digits')
        .max(8, 'Must be at most 8 digits')
    }),
    execute: async ({ hs_code }) => {
      // Check cache first
      if (searchCache.has(hs_code)) {
        console.log('🔄 Using cached search result:', { hs_code });
        return searchCache.get(hs_code);
      }

      console.log('🔍 Tariff lookup:', {
        code: hs_code,
        digits: hs_code.length,
        timestamp: new Date().toISOString()
      });
      
      try {
        const response = await fetch(`https://api.clear.ai/api/v1/au_tariff/tariffs/chapter_flatten_tariffs?code=${hs_code}`);
        
        if (!response.ok) {
          throw new Error(`API request failed: ${response.status}`);
        }

        const data = await response.json();
        
        // Cache the response
        searchCache.set(hs_code, JSON.stringify(data));
        
        console.log('📊 Lookup results:', {
          code: hs_code,
          matches: data?.length ?? 0,
          timestamp: new Date().toISOString()
        });

        return JSON.stringify(data);
        
      } catch (error) {
        console.error('❌ API Error:', {
          error,
          hs_code,
          timestamp: new Date().toISOString()
        });
        return JSON.stringify([]);
      }
    }
  }),

  search_product_info: tool({
    description: 'Search for detailed product information when brand names are detected.',
    inputSchema: z.object({
      brand: z.string().min(2),
      product_description: z.string().min(1)
    }),
    execute: async ({ brand, product_description }) => {
      console.log('🔍 search_product_info called:', {
        timestamp: new Date().toISOString(),
        brand,
        product_description
      });

      const searchKey = `${brand}-${product_description}`.toLowerCase();
      
      if (searchCache.has(searchKey)) {
        console.log('🔄 Using cached search result:', { 
          brand, 
          product_description,
          cacheKey: searchKey 
        });
        return searchCache.get(searchKey);
      }

      try {
        const query = `${brand} ${product_description} specifications materials composition official`;
        console.log('🔎 Tavily search query:', {
          query,
          timestamp: new Date().toISOString()
        });
        
        const searchResponse = await tvly.search(query, {
          searchDepth: "advanced",
          maxResults: 3,
          includeRawContent: 'text',
          includeImages: true,
          includeImageDescriptions: true,
          includeDomains: [],
          excludeDomains: ["facebook.com", "twitter.com", "instagram.com"],
        });

        // Limit the raw content to 10000 characters
        if (searchResponse?.results?.length) {
          searchResponse.results.forEach(result => {
            if (result.rawContent) {
              result.rawContent = result.rawContent.substring(0, 10000);
            }
          });
        }

        console.log('📊 Tavily raw response:', {
          timestamp: new Date().toISOString(),
          hasResults: !!searchResponse?.results?.length,
          resultCount: searchResponse?.results?.length,
          imageCount: searchResponse?.images?.length,
          firstResultTitle: searchResponse?.results?.[0]?.title
        });

        if (!searchResponse?.results?.length) {
          console.log('⚠️ No search results found');
          return JSON.stringify({ content: 'No product information found' });
        }

        // Format the text response
        let formattedContent = 'Real-time product research results:\n\n';
        
        searchResponse.results.forEach((result, index) => {
          formattedContent += `🔍 [${result.title}](${result.url}) (Relevancy: ${(result.score * 100).toFixed(0)}%)\n`;
          formattedContent += `${result.rawContent || result.content}\n\n`;
        });

        // Create the structured response
        const response: ToolResult = {
          content: formattedContent,
          images: searchResponse.images?.map(image => ({
            url: image.url,
            description: image.description || `${brand} ${product_description}`
          }))
        };

        console.log('🔧 Pre-validation response structure:', {
          hasContent: !!response.content,
          contentLength: response.content.length,
          imageCount: response.images?.length
        });

        // Validate response
        try {
          const validated = toolResultSchema.parse(response);
          console.log('✅ Schema validation passed');
          
          // Cache the validated response
          const jsonResponse = JSON.stringify(validated);
          searchCache.set(searchKey, jsonResponse);
          
          console.log('📤 Final tool response:', {
            timestamp: new Date().toISOString(),
            responseLength: jsonResponse.length,
            cacheKey: searchKey
          });

          return jsonResponse;
        } catch (validationError) {
          console.error('❌ Schema validation failed:', {
            error: validationError,
            response
          });
          throw validationError;
        }

      } catch (error) {
        console.error('❌ Product search error:', {
          error,
          brand,
          product_description,
          timestamp: new Date().toISOString(),
          errorType: error instanceof Error ? error.constructor.name : typeof error,
          errorMessage: error instanceof Error ? error.message : String(error)
        });
        
        return JSON.stringify({
          content: 'Error retrieving product information',
          error: error instanceof Error ? error.message : 'Unknown error'
        });
      }
    }
  }),

  extract_url_content: tool({
    description: 'Extract readable page content and images from a single URL (product page or spec sheet).',
    inputSchema: z.object({
      url: z.string().describe('The URL user provided'),
    }),
    execute: async ({ url }) => {
      type TavilyExtractItem = {
        url?: string;
        raw_content?: string;
        rawContent?: string;
        content?: string;
        images?: string[];
      };
      type TavilyExtractResponse = { results?: TavilyExtractItem[] };

      try {
        const res: TavilyExtractResponse = await (tvly as any).extract(
          [url],
          {
            includeImages: true,
            extractDepth: 'advanced',
            format: 'markdown',
            includeFavicon: false,
            timeout: 60,
          }
        );

        const first = res?.results?.[0] ?? {};
        const rawText = first.raw_content ?? first.rawContent ?? first.content ?? '';
        const text = rawText.length > 10000 ? rawText.substring(0, 10000) + '...' : rawText;
        const images = Array.isArray(first.images)
          ? first.images.map((imgUrl: string) => ({ url: imgUrl, description: imgUrl }))
          : [];
        console.log('🔍 Tavily extract response:', first);
        const response: ToolResult = { content: String(text || ''), images };
        const validated = toolResultSchema.parse(response);
        return JSON.stringify(validated);
      } catch (error) {
        console.error('❌ Tavily extract error:', { error, url });
        return JSON.stringify({ content: `Error extracting content from URL: ${url}` });
      }
    },
  }),

  tariff_concession_lookup: tool({
    description: 'Look up specific Schedule 4 concession information by by-law number. Use ONLY when user asks about items that may qualify for Schedule 4 concessional rates (scientific goods, personal effects, international organization goods, etc.). Only use if the item matches known Schedule 4 categories.',
    inputSchema: z.object({
      bylaw_number: z.string().regex(/^\d+$/, 'Must be a numeric by-law number (e.g., 1700581, 2300091)')
    }),
    execute: async ({ bylaw_number }) => {
      console.log('🔍 Schedule 4 Concession Lookup:', {
        timestamp: new Date().toISOString(),
        bylaw_number,
        apiUrl: `https://api.clear.ai/api/v1/au_tariff/book_nodes/search?term=${bylaw_number}&book_ref=AU_TARIFF_SCHED4_2022`
      });

      // Check cache first
      const cacheKey = `schedule4_${bylaw_number}`;
      if (searchCache.has(cacheKey)) {
        console.log('🔄 Using cached Schedule 4 result:', { bylaw_number });
        return searchCache.get(cacheKey);
      }

      try {
        const response = await fetch(`https://api.clear.ai/api/v1/au_tariff/book_nodes/search?term=${bylaw_number}&book_ref=AU_TARIFF_SCHED4_2022`);
        
        if (!response.ok) {
          throw new Error(`Schedule 4 API request failed: ${response.status}`);
        }

        const rawData = await response.json();
        
        console.log('📡 Schedule 4 API Response:', {
          timestamp: new Date().toISOString(),
          bylaw_number,
          hasResults: !!rawData?.results?.length,
          resultCount: rawData?.results?.length || 0
        });

        const cleanedData = cleanupTariffData(rawData);
        
        console.log('🧹 Schedule 4 Data Cleaned:', {
          bylaw_number,
          originalSize: JSON.stringify(rawData).length,
          cleanedSize: JSON.stringify(cleanedData).length,
          timestamp: new Date().toISOString()
        });

        // Cache the cleaned response
        const jsonResponse = JSON.stringify(cleanedData);
        searchCache.set(cacheKey, jsonResponse);
        
        console.log('📤 Schedule 4 Response Cached:', {
          bylaw_number,
          responseLength: jsonResponse.length,
          cacheKey,
          timestamp: new Date().toISOString()
        });

        return jsonResponse;
        
      } catch (error) {
        console.error('❌ Schedule 4 API Error:', {
          error,
          bylaw_number,
          timestamp: new Date().toISOString(),
          errorType: error instanceof Error ? error.constructor.name : typeof error,
          errorMessage: error instanceof Error ? error.message : String(error)
        });
        
        return JSON.stringify({
          content: 'Error retrieving Schedule 4 concession information',
          error: error instanceof Error ? error.message : 'Unknown error',
          results: []
        });
      }
    }
  })
};

// Export individual tools if needed
export const { tariff_chapter_lookup, tariff_search, search_product_info, extract_url_content, tariff_concession_lookup } = auTariffTools;
