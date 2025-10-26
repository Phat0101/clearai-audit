import { tool } from 'ai';
import { z } from 'zod';
import { tavily } from '@tavily/core';
import { toolResultSchema, ToolResult } from '@/types/search';

// Initialize Tavily client
const tvly = tavily({ apiKey: process.env.TAVILY_API_KEY! });

// Track searches to prevent duplicates
const searchCache = new Map();

/**
 * New Zealand tariff classification tools for AI chat
 */
export const nzTariffTools = {
  tariff_chapter_lookup: tool({
    description:
      'Look up all HS Codes that belong to your selected 4-digit chapter for New Zealand. Use ONLY AFTER stating your chapter selection.',
    inputSchema: z.object({
      hs_code: z.string().length(4).regex(/^\d+$/, 'Must be a 4-digit chapter code'),
    }),
    execute: async ({ hs_code }) => {
      try {
        // Also return chapter notes and section notes
        const url = `https://api.clear.ai/api/v1/au_tariff/tariffs/chapter_flatten_tariffs?code=${hs_code}&book_ref=NZ_INTRODUCTION_HS_2022`;
        const response = await fetch(url);
        if (!response.ok) {
          throw new Error(`NZ chapter lookup failed: ${response.status}`);
        }
        const data = await response.json();
        return JSON.stringify(data);
      } catch (error) {
        console.error('❌ NZ chapter lookup error:', error);
        return JSON.stringify({ error: 'Error retrieving NZ chapter information' });
      }
    },
  }),

  tariff_search: tool({
    description:
      'Detailed lookup for specific NZ HS codes (2-8 digits). Use ONLY when user provides specific HS codes to look up. Only run once at a time.',
    inputSchema: z.object({
      hs_code: z
        .string()
        .regex(/^\d+$/, 'Must be numeric HS code')
        .min(2, 'Must be at least 2 digits')
        .max(8, 'Must be at most 8 digits'),
    }),
    execute: async ({ hs_code }) => {
      const cacheKey = `nz_${hs_code}`;
      if (searchCache.has(cacheKey)) {
        return searchCache.get(cacheKey);
      }
      try {
        const url = `https://api.clear.ai/api/v1/au_tariff/tariffs/chapter_flatten_tariffs?code=${hs_code}&book_ref=NZ_INTRODUCTION_HS_2022`;
        const response = await fetch(url);
        if (!response.ok) {
          throw new Error(`NZ tariff search failed: ${response.status}`);
        }
        const data = await response.json();
        // Return raw API payload (array)
        const result = JSON.stringify(data);
        searchCache.set(cacheKey, result);
        return result;
      } catch (error) {
        console.error('❌ NZ tariff search error:', { error, hs_code });
        const err = JSON.stringify({ error: 'Error retrieving NZ product information' });
        searchCache.set(cacheKey, err);
        return err;
      }
    },
  }),

  search_product_info: tool({
    description: 'Search for detailed product information when brand names are detected.',
    inputSchema: z.object({
      brand: z.string().min(2),
      product_description: z.string().min(1),
    }),
    execute: async ({ brand, product_description }) => {
      const key = `nz_brand_${brand}-${product_description}`.toLowerCase();
      if (searchCache.has(key)) {
        return searchCache.get(key);
      }
      try {
        const query = `${brand} ${product_description} specifications materials composition official`;
        const searchResponse = await tvly.search(query, {
          searchDepth: 'advanced',
          maxResults: 3,
          includeRawContent: 'text',
          includeImages: true,
          includeImageDescriptions: true,
          includeDomains: [],
          excludeDomains: ['facebook.com', 'twitter.com', 'instagram.com'],
        });

        if (searchResponse?.results?.length) {
          searchResponse.results.forEach((r) => {
            if (r.rawContent) r.rawContent = r.rawContent.substring(0, 10000);
          });
        }

        if (!searchResponse?.results?.length) {
          const noRes = JSON.stringify({ content: 'No product information found' });
          searchCache.set(key, noRes);
          return noRes;
        }

        let formattedContent = 'Real-time product research results:\n\n';
        searchResponse.results.forEach((result) => {
          formattedContent += `🔍 [${result.title}](${result.url}) (Relevancy: ${(result.score * 100).toFixed(0)}%)\n`;
          formattedContent += `${result.rawContent || result.content}\n\n`;
        });

        const response: ToolResult = {
          content: formattedContent,
          images: searchResponse.images?.map((img) => ({
            url: img.url,
            description: img.description || `${brand} ${product_description}`,
          })),
        };

        const validated = toolResultSchema.parse(response);
        const json = JSON.stringify(validated);
        searchCache.set(key, json);
        return json;
      } catch (error) {
        console.error('❌ NZ product search error:', { error, brand, product_description });
        return JSON.stringify({ content: 'Error retrieving product information' });
      }
    },
  }),
  
  extract_url_content: tool({
    description: 'Extract readable page content and images from a single URL (NZ context).',
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
      const MAX_LENGTH = 10000;

      const toJsonToolResult = (text: string, imageUrls?: string[]) => {
        const clipped = (text || '').length > MAX_LENGTH
          ? (text || '').substring(0, MAX_LENGTH) + '...'
          : (text || '');
        const images = Array.isArray(imageUrls)
          ? imageUrls.map((imgUrl: string) => ({ url: imgUrl, description: imgUrl }))
          : [];
        const response: ToolResult = { content: String(clipped), images };
        const validated = toolResultSchema.parse(response);
        return JSON.stringify(validated);
      };

      const tryTavily = async (depth: 'basic' | 'advanced') => {
        try {
          if (typeof (tvly as any)?.extract !== 'function') {
            console.warn('⚠️ Tavily extract not available on this client. Skipping.');
            return { ok: false as const };
          }
          const res: TavilyExtractResponse = await (tvly as any).extract([url], {
            includeImages: true,
            extractDepth: depth,
            format: 'markdown',
            includeFavicon: false,
            timeout: 60,
          });
          const first = res?.results?.[0] ?? {};
          const rawText = (first as any).raw_content ?? (first as any).rawContent ?? (first as any).content ?? '';
          const text = typeof rawText === 'string' ? rawText : '';
          const images = Array.isArray(first.images) ? first.images : [];
          console.log('🔍 NZ Tavily extract response:', { depth, hasText: !!text?.trim(), imageCount: images.length });
          if (text && text.trim().length > 0) {
            return { ok: true as const, text, images };
          }
          return { ok: false as const };
        } catch (error) {
          console.error('❌ NZ Tavily extract attempt failed:', { depth, url, error });
          return { ok: false as const };
        }
      };

      // 1) Try advanced extraction first
      const advanced = await tryTavily('advanced');
      if (advanced.ok) {
        return toJsonToolResult(advanced.text as string, advanced.images as string[]);
      }

      // 2) Fallback to basic extraction
      const basic = await tryTavily('basic');
      if (basic.ok) {
        return toJsonToolResult(basic.text as string, basic.images as string[]);
      }

      // 3) Final fallback: Jina Reader
      try {
        const target = new URL(url);
        const readerUrl = `https://r.jina.ai/http://${target.host}${target.pathname}${target.search}`;
        const r = await fetch(readerUrl, {
          headers: {
            'User-Agent': 'Mozilla/5.0 (compatible; TariffChatBot/1.0; +https://tariff.chat)',
          }
        });
        if (r.ok) {
          const readerText = await r.text();
          if (readerText && readerText.trim().length > 0) {
            console.log('✅ NZ Jina Reader fallback succeeded');
            return toJsonToolResult(readerText);
          }
          console.warn('⚠️ NZ Jina Reader returned empty content', { status: r.status });
        } else {
          console.warn('⚠️ NZ Jina Reader request failed', { status: r.status });
        }
      } catch (fallbackError) {
        console.error('❌ NZ Jina Reader fallback error:', { url, error: fallbackError });
      }

      return JSON.stringify({ content: `Error extracting content from URL: ${url}` });
    },
  }),
};

export const { tariff_chapter_lookup, tariff_search, search_product_info, extract_url_content } = nzTariffTools;


