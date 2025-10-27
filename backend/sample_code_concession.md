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
  }),