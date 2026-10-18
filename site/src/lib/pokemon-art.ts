// Browser side of PokemonImage.astro: the fallback chain for Pokémon images, shared with pages that draw
// thumbnails in the browser (the trainer directory). data-art="<id>" marks the 96 px sprite (next: HOME artwork,
// then the official artwork); "<id>h" HOME artwork (next: official); "<id>o" the official artwork (next: a placeholder).
import { artworkUrl, fallbackArtworkUrl, spriteUrl } from '../../../work/save-editor/src/ui/artwork';

function nextArtwork(img: HTMLImageElement) {
  const value = img.dataset.art ?? '';
  const id = Number.parseInt(value, 10);
  if (!id) return null;
  if (/^\d+$/.test(value)) { img.dataset.art = `${id}h`; img.classList.remove('pokemon-sprite'); return artworkUrl(id, false); }
  if (value.endsWith('h')) { img.dataset.art = `${id}o`; return fallbackArtworkUrl(id, false); }
  return null;
}

export function setupArtwork(root: ParentNode = document) {
  root.querySelectorAll<HTMLImageElement>('img[data-art]').forEach(img => {
    if (img.dataset.artworkReady) return;
    img.dataset.artworkReady = '1';
    const failed = () => {
      const fallback = nextArtwork(img);
      if (fallback) img.src = fallback;
      else { const span = document.createElement('span'); span.className = 'art-placeholder'; span.textContent = '—'; if (img.alt) { span.setAttribute('role', 'img'); span.setAttribute('aria-label', `${img.alt}: image unavailable`); } else span.setAttribute('aria-hidden', 'true'); img.replaceWith(span); }
    };
    img.addEventListener('error', failed);
    if (img.complete && img.naturalWidth === 0) failed();
  });
}

/** A decorative 48 px sprite thumbnail, the same markup as <PokemonImage> (call setupArtwork after inserting it). */
export function spriteThumb(baseSpeciesId: number, inline = false) {
  const tag = inline ? 'span' : 'figure';
  const img = document.createElement('img');
  Object.assign(img, { src: spriteUrl(baseSpeciesId), alt: '', width: 48, height: 48, loading: 'lazy', decoding: 'async', className: 'pokemon-sprite' });
  img.dataset.art = String(baseSpeciesId);
  img.setAttribute('aria-hidden', 'true');
  const frame = document.createElement(tag);
  frame.className = 'pokemon-image pokemon-image-small';
  frame.append(img);
  return frame;
}
