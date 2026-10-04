import { defineCollection } from 'astro:content';
import { z } from 'astro/zod';
import { docsLoader } from '@astrojs/starlight/loaders';
import { docsSchema } from '@astrojs/starlight/schema';

export const collections = {
	docs: defineCollection({
		loader: docsLoader(),
		// `source`: the file in the main repo this page is generated from (for edit links).
		schema: docsSchema({ extend: z.object({ source: z.string().optional() }) }),
	}),
};
