import { defineCollection } from 'astro:content';
import { z } from 'astro/zod';
import { docsLoader } from '@astrojs/starlight/loaders';
import { docsSchema } from '@astrojs/starlight/schema';

export const collections = {
	docs: defineCollection({
		loader: docsLoader(),
		// `source`: the file in the main repo this page is generated from (for edit links).
		// `seo`: search-only overrides read by src/routeData.ts: the <title> page part (the visible H1 stays `title`)
		// and a canonical path (without the base) when the page duplicates another one.
		schema: docsSchema({ extend: z.object({
			source: z.string().optional(),
			seo: z.object({ title: z.string().optional(), canonical: z.string().optional() }).optional(),
		}) }),
	}),
};
