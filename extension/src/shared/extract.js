/**
 * Listing extraction, most-reliable source first.
 *
 * Shopee is a single-page app with obfuscated, frequently-rotated class names,
 * so DOM-first scraping is brittle by construction. We therefore prefer the
 * PDP JSON API (same-origin from the page, so cookies attach and CORS is a
 * non-issue) and keep DOM scraping as a fallback that anchors on semantic
 * structure and text shape rather than class names.
 */
(function (root) {
  root.Sentinel = root.Sentinel || {};
  const { config } = root.Sentinel;

  /** Parse `-i.{shopId}.{itemId}` — note shopId comes FIRST. */
  function parseProductUrl(href = location.href) {
    const match = config.productUrlPattern.exec(href);
    if (!match) return null;
    return { shopId: match[1], itemId: match[2] };
  }

  function imageUrl(hash) {
    if (!hash) return null;
    if (/^https?:\/\//.test(hash)) return hash;
    return config.imageCdnBase + hash;
  }

  function normalisePrice(raw) {
    if (typeof raw !== "number" || !Number.isFinite(raw) || raw <= 0) return null;
    return raw / config.priceScale;
  }

  // --- Layer 1: PDP JSON API -----------------------------------------------

  async function fromPdpApi({ itemId, shopId }) {
    const url = config.pdpApiTemplate
      .replace("{itemId}", itemId)
      .replace("{shopId}", shopId);

    const response = await fetch(url, {
      credentials: "include",
      headers: { "x-api-source": "pc", "x-requested-with": "XMLHttpRequest" },
    });
    if (!response.ok) throw new Error(`PDP API ${response.status}`);

    const body = await response.json();
    const item = body?.data?.item ?? body?.item;
    if (!item) throw new Error("PDP API returned no item");

    const specs = {};
    for (const attr of item.attributes ?? []) {
      if (attr?.name && attr?.value) specs[attr.name] = String(attr.value);
    }
    if (item.weight) specs.weight = `${item.weight} kg`;
    const dims = item.dimension;
    if (dims?.width && dims?.length && dims?.height) {
      specs.dimensions = `${dims.length}x${dims.width}x${dims.height} cm`;
    }

    const gallery = (item.images ?? [])
      .slice(0, config.maxGalleryImages)
      .map(imageUrl)
      .filter(Boolean);

    return {
      source: "pdp-api",
      itemId,
      shopId,
      title: item.title ?? item.name ?? "",
      price:
        normalisePrice(item.price) ??
        normalisePrice(item.price_min) ??
        null,
      originalPrice:
        normalisePrice(item.price_before_discount) ?? null,
      sellerRating: item.shop_rating ?? item.item_rating?.rating_star ?? null,
      shopLocation: item.shop_location ?? null,
      specs,
      imageUrls: gallery,
      reviewImageUrls: [],
    };
  }

  /**
   * The heading that starts the customer-review section.
   *
   * Splits the page in two: product imagery above it, buyer photos and
   * review text below. Matched on heading TEXT, not class names, which
   * Shopee obfuscates and rotates.
   */
  function findReviewAnchor() {
    const reviewHeadingRe = /\b(review|rating|ulasan|penilaian)\b/i;
    for (const el of document.querySelectorAll(
      "h1,h2,h3,h4,section,div[class],[role='heading']"
    )) {
      const own = (el.childElementCount ? "" : el.textContent || "").trim();
      if (own && own.length < 60 && reviewHeadingRe.test(own)) return el;
    }
    return null;
  }

  // --- Reviews --------------------------------------------------------------

  /**
   * Normalise one review's text, or reject it.
   *
   * Empty and one-or-two-word reviews are discarded: "ok", "good", "fast
   * delivery" say nothing about whether the product matches its listing, and
   * they are exactly what review farms mass-produce. Requiring a real sentence
   * keeps the evidence and cuts the token bill.
   */
  function usableReviewText(raw) {
    const text = String(raw || "").replace(/\s+/g, " ").trim();
    if (text.length < config.minReviewChars) return null;
    if (text.split(" ").filter(Boolean).length < config.minReviewWords) return null;
    return text;
  }

  /** Collapse a review to a comparable form, for spotting repeats. */
  function reviewFingerprint(text) {
    return text
      .toLowerCase()
      .replace(/[^a-z0-9 ]/g, "")
      .split(" ")
      .filter(Boolean)
      .slice(0, 12)
      .join(" ");
  }

  /**
   * Turn raw rating records into the payload's reviews plus population stats.
   *
   * The stats describe what existed *before* filtering, because "400 reviews
   * of which 6 have text" and "6 reviews all with text" mean very different
   * things, and the survivors alone cannot distinguish them.
   */
  function summariseReviews(records) {
    const stats = {
      totalFound: records.length,
      usable: 0,
      discardedTooShort: 0,
      duplicateGroups: 0,
      averageRating: null,
    };

    const stars = records.map((r) => r.rating).filter((n) => typeof n === "number");
    if (stars.length) {
      stats.averageRating =
        Math.round((stars.reduce((a, b) => a + b, 0) / stars.length) * 10) / 10;
    }

    const byFingerprint = new Map();
    const kept = [];

    for (const record of records) {
      const text = usableReviewText(record.text);
      if (!text) {
        stats.discardedTooShort += 1;
        continue;
      }

      const fp = reviewFingerprint(text);
      const count = (byFingerprint.get(fp) || 0) + 1;
      byFingerprint.set(fp, count);

      // Send one copy of a repeated review; the repetition is reported via
      // duplicateGroups rather than by paying to send it many times.
      if (count === 1 && kept.length < config.maxReviews) {
        kept.push({
          text: text.slice(0, 600),
          rating: typeof record.rating === "number" ? record.rating : null,
          hasImages: Boolean(record.hasImages),
        });
      }
    }

    stats.usable = kept.length;
    stats.duplicateGroups = [...byFingerprint.values()].filter((n) => n > 1).length;
    return { reviews: kept, reviewStats: stats };
  }

  /** One page of ratings, with a specific error when Shopee refuses. */
  async function fetchRatingsPage({ itemId, shopId }, offset, limit) {
    const url = config.ratingsApiTemplate
      .replace("{itemId}", itemId)
      .replace("{shopId}", shopId)
      .replace("{limit}", String(limit))
      .replace("{offset}", String(offset));

    const response = await fetch(url, {
      credentials: "include",
      headers: { "x-api-source": "pc", "x-requested-with": "XMLHttpRequest" },
    });
    if (!response.ok) {
      throw new Error(`ratings API HTTP ${response.status} (offset ${offset})`);
    }

    const body = await response.json();

    // Shopee answers 200 with an error code in the body, so a raw status
    // check is not enough to know the call worked.
    if (body?.error) {
      throw new Error(
        `ratings API error ${body.error}${body.error_msg ? `: ${body.error_msg}` : ""}`
      );
    }

    const ratings = body?.data?.ratings;
    if (!Array.isArray(ratings)) {
      throw new Error(
        `ratings API returned no list (data keys: ${
          body?.data ? Object.keys(body.data).join(",") : "none"
        })`
      );
    }
    return ratings;
  }

  /**
   * Every page of reviews, up to a cap.
   *
   * Paging matters: Shopee's default ordering puts plenty of empty five-star
   * ratings first, so the reviews that actually say something are frequently
   * not on page one. Stops as soon as a page comes back short.
   */
  async function fromRatingsApi(ids) {
    const size = config.ratingsPageSize;
    const all = [];
    let pagesFetched = 0;

    for (let page = 0; page < config.maxRatingPages; page++) {
      let batch;
      try {
        batch = await fetchRatingsPage(ids, page * size, size);
      } catch (err) {
        // A later page failing should not discard the pages that worked.
        if (page === 0) throw err;
        console.warn(`[Sentinel] ratings page ${page} failed:`, String(err));
        break;
      }
      pagesFetched += 1;
      all.push(...batch);
      if (batch.length < size) break;
    }

    const records = all.map((r) => ({
      text: r?.comment,
      rating: r?.rating_star,
      hasImages: Array.isArray(r?.images) && r.images.length > 0,
    }));

    const images = [];
    for (const r of all) {
      for (const hash of r?.images ?? []) {
        if (images.length >= config.maxReviewImages) break;
        const u = imageUrl(hash);
        if (u) images.push(u);
      }
    }

    const withText = records.filter((r) => (r.text || "").trim().length > 0).length;
    console.info(
      `[Sentinel] ratings API: ${all.length} reviews over ${pagesFetched} page(s),`,
      `${withText} with any comment text,`,
      `${images.length} buyer photo(s)`
    );

    return { ...summariseReviews(records), reviewImageUrls: images };
  }

  /** Last resort: pull review paragraphs out of the DOM. */
  function reviewsFromDom() {
    const anchorEl = findReviewAnchor();
    if (!anchorEl) return { reviews: [], reviewStats: null };

    const records = [];
    const seen = new Set();
    for (const el of document.querySelectorAll("div, p, span, li")) {
      const after =
        anchorEl.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING;
      if (!after) continue;
      // Innermost text only: a container would swallow the whole section.
      if (el.childElementCount > 0) continue;

      const text = (el.textContent || "").trim();
      if (text.length < config.minReviewChars || text.length > 800) continue;
      if (seen.has(text)) continue;
      seen.add(text);
      records.push({ text, rating: null, hasImages: false });
    }
    return summariseReviews(records);
  }

// --- Layer 2: DOM fallback -----------------------------------------------

  /** Extract pristine data from hidden SEO JSON-LD tags */
  function getStructuredData() {
    const scripts = document.querySelectorAll('script[type="application/ld+json"]');
    for (const script of scripts) {
      try {
        const data = JSON.parse(script.textContent);
        // Look specifically for the Product schema
        if (data['@type'] === 'Product') {
          return {
            title: data.name || null,
            // Convert price to a float, just in case it's a string
            price: data.offers?.price ? parseFloat(data.offers.price) : null,
          };
        }
      } catch (error) {
        console.debug("[Sentinel] Skipped unparseable JSON-LD block");
      }
    }
    return null;
  }
  /** Largest-text heading, rather than a class name that changes weekly. */
  function scrapeTitle() {
    const candidates = [
      ...document.querySelectorAll("h1, [data-sqe='name'], section h2"),
    ];
    const best = candidates
      .map((el) => ({ el, text: (el.textContent || "").trim() }))
      .filter((c) => c.text.length > 8 && c.text.length < 300)
      .sort((a, b) => b.text.length - a.text.length)[0];
    return best ? best.text : document.title.replace(/\s*\|\s*Shopee.*$/i, "");
  }

  /** Find SGD amounts by text shape, then take the most prominent. */
  function scrapePrices() {
    const priceRe = /(?:S\$|\$)\s?([\d,]+(?:\.\d{1,2})?)/;
    const found = [];

    const walker = document.createTreeWalker(
      document.body,
      NodeFilter.SHOW_TEXT
    );
    let node;
    while ((node = walker.nextNode())) {
      const text = node.nodeValue?.trim();
      if (!text || text.length > 40) continue;
      const m = priceRe.exec(text);
      if (!m) continue;

      const value = parseFloat(m[1].replace(/,/g, ""));
      if (!Number.isFinite(value) || value <= 0) continue;

      const el = node.parentElement;
      const size = el ? parseFloat(getComputedStyle(el).fontSize) || 0 : 0;
      const struck =
        el && /line-through/.test(getComputedStyle(el).textDecorationLine);
      found.push({ value, size, struck });
    }
    if (!found.length) return { price: null, originalPrice: null };

    const current = found
      .filter((f) => !f.struck)
      .sort((a, b) => b.size - a.size)[0];
    const original = found
      .filter((f) => f.struck)
      .sort((a, b) => b.value - a.value)[0];

    return {
      price: current ? current.value : found[0].value,
      originalPrice: original ? original.value : null,
    };
  }

  function scrapeSpecs() {
    const specs = {};
    // Specification tables render as label/value pairs; pair adjacent cells.
    for (const row of document.querySelectorAll("tr, [role='row'], li")) {
      const cells = [...row.children];
      if (cells.length !== 2) continue;
      const key = (cells[0].textContent || "").trim();
      const value = (cells[1].textContent || "").trim();
      if (key && value && key.length < 40 && value.length < 200) {
        specs[key] = value;
      }
    }
    return specs;
  }

  // Everything on a Shopee page is served from susercontent.com — the user's
  // own avatar, voucher tiles, category icons, promotional banners and the
  // "you may also like" carousel included. Sending those to the model is worse
  // than sending nothing: it reports on a profile picture instead of the
  // product, and the whole verdict becomes nonsense.
  const AVATAR_HINT = /avatar|profile|portrait|logo|badge|icon|banner|voucher|promo|ads?\b|shopee/i;

  // Review thumbnails render around 80px; commenter avatars around 40px.
  const MIN_RENDERED_PX = 64;
  // Banners are far wider than tall. Product photography is roughly square.
  const MIN_RATIO = 0.45;
  const MAX_RATIO = 2.2;

  /** Why this image is not product imagery, or null if it qualifies. */
  function rejectionReason(img) {
    const rect = img.getBoundingClientRect();
    // Fall back to intrinsic size for images not yet laid out.
    const w = Math.round(rect.width) || img.naturalWidth;
    const h = Math.round(rect.height) || img.naturalHeight;

    if (!w || !h) return "no size";
    if (w < MIN_RENDERED_PX || h < MIN_RENDERED_PX) return "too small (icon/avatar)";

    const ratio = w / h;
    if (ratio > MAX_RATIO) return "too wide (banner)";
    if (ratio < MIN_RATIO) return "too tall (banner)";

    // Site chrome: headers, navigation, footers, floating toolbars.
    if (img.closest("header, nav, footer, [role='banner'], [role='navigation']")) {
      return "page furniture";
    }

    // Avatars are circular far more often than product photos are.
    const radius = getComputedStyle(img).borderRadius || "";
    if (/^(50%|9999px|[5-9]\d%)/.test(radius)) return "circular (avatar)";

    // A link to a DIFFERENT product means a recommendation or advert, not
    // this listing. The current product's own id is allowed through.
    const href = img.closest("a[href]")?.getAttribute("href") || "";
    const linked = config.productUrlPattern.exec(href);
    if (linked) {
      const here = parseProductUrl();
      if (!here || linked[2] !== here.itemId) return "links to another product";
    }

    // Last resort, and deliberately weak: Shopee's class names are obfuscated,
    // but alt text and ARIA labels sometimes still say what a thing is.
    const described = [
      img.alt,
      img.getAttribute("aria-label"),
      img.closest("[aria-label]")?.getAttribute("aria-label"),
    ]
      .filter(Boolean)
      .join(" ");
    if (described && AVATAR_HINT.test(described)) return "labelled as non-product";

    return null;
  }

  /**
   * Split product images from customer review photos.
   *
   * Splitting matters: comparing seller gallery against buyer photos is the
   * strongest bait-and-switch signal there is, so handing the model two
   * mislabelled groups is worse than sending fewer images. We locate the
   * review section by its heading text and treat anything at or after it in
   * document order as a review photo.
   */
  function scrapeImages() {
    const reviewAnchor = findReviewAnchor();

    const gallery = [];
    const review = [];
    const seen = new Set();
    const rejected = [];

    for (const img of document.querySelectorAll("img")) {
      const src = img.currentSrc || img.src;
      if (!src || !src.includes("susercontent.com")) continue;

      const reason = rejectionReason(img);
      if (reason) {
        rejected.push({ reason, src: src.slice(-40) });
        continue;
      }

      const url = src.split("_tn")[0];
      if (seen.has(url)) continue;
      seen.add(url);

      const isAfterAnchor =
        reviewAnchor &&
        reviewAnchor.compareDocumentPosition(img) &
          Node.DOCUMENT_POSITION_FOLLOWING;

      (isAfterAnchor ? review : gallery).push(url);
    }

    if (rejected.length) {
      const counts = {};
      for (const r of rejected) counts[r.reason] = (counts[r.reason] || 0) + 1;
      console.info("[Sentinel] filtered out non-product images:", counts);
    }

    return { gallery, review };
  }

  function fromDom({ itemId, shopId }) {
    // 1. Grab the structured data (Gold standard for DOM reading)
    const structured = getStructuredData() || {};
    
    // 2. Run the visual scrapers for things SEO data doesn't provide
    const visualPrices = scrapePrices();
    const { gallery, review } = scrapeImages();

    return {
      source: "dom",
      itemId,
      shopId,
      // Prefer structured title, fallback to visual heading scraper
      title: structured.title || scrapeTitle(),
      // Prefer structured price, fallback to visual price scraper
      price: structured.price || visualPrices.price,
      // JSON-LD rarely has the struck-through original price, so we still use visual for this
      originalPrice: visualPrices.originalPrice,
      sellerRating: null,
      shopLocation: null,
      specs: scrapeSpecs(),
      // We still use visual scraping for images because JSON-LD does NOT contain customer review photos!
      imageUrls: gallery.slice(0, config.maxGalleryImages),
      reviewImageUrls: review.slice(0, config.maxReviewImages),
    };
  }

  // --- Orchestration --------------------------------------------------------

  async function extractListing(retries = 4) {
    const ids = parseProductUrl();
    if (!ids) return null;

    let listing = null;
    let apiError = null;
    try {
      listing = await fromPdpApi(ids);
    } catch (err) {
      // console.warn, not console.debug: Chrome hides Verbose by default, so a
      // debug-level failure is invisible exactly when someone is trying to
      // work out why nothing happened.
      apiError = String(err?.message || err);
      console.warn("[Sentinel] PDP API unavailable, falling back to DOM:", apiError);
    }

    // Written reviews are the one place a buyer says what actually arrived.
    // The ratings endpoint also attributes buyer photos per review, which DOM
    // scraping cannot do reliably.
    let reviewData = { reviews: [], reviewStats: null, reviewImageUrls: [] };
    try {
      reviewData = await fromRatingsApi(ids);
    } catch (err) {
      console.warn("[Sentinel] ratings API unavailable, scraping DOM:", String(err));
      try {
        reviewData = { ...reviewsFromDom(), reviewImageUrls: [] };
      } catch (domErr) {
        console.warn("[Sentinel] DOM review scrape failed:", String(domErr));
      }
    }

    // The API can succeed but omit fields; fill gaps from the DOM rather than
    // sending a half-empty payload the model cannot reason about.
    const domData = fromDom(ids);

    if (!listing) {
      listing = domData;
    } else {
      listing.title ||= domData.title;
      listing.price ??= domData.price;
      listing.originalPrice ??= domData.originalPrice;
      if (!Object.keys(listing.specs).length) listing.specs = domData.specs;
      if (!listing.imageUrls.length) listing.imageUrls = domData.imageUrls;
      if (!listing.reviewImageUrls.length) {
        listing.reviewImageUrls = domData.reviewImageUrls;
      }
    }

    // Ratings-API photos are correctly attributed, so they win outright.
    if (reviewData.reviewImageUrls?.length) {
      listing.reviewImageUrls = reviewData.reviewImageUrls;
    }

    // --- NEW RETRY LOGIC: Wait for Shopee to load the JSON-LD ---
    if (!listing.title || listing.price == null) {
      if (retries > 0) {
        console.debug(`[Sentinel] Data not ready, retrying... (${retries} left)`);
        await new Promise(resolve => setTimeout(resolve, 800)); // wait 800ms
        return extractListing(retries - 1); // Try again
      }
      console.warn("[Sentinel] could not read this listing", {
        missing: [
          !listing.title && "title",
          listing.price == null && "price",
        ].filter(Boolean),
        source: listing.source,
        pdpApiError: apiError,
        ids,
        sawTitle: listing.title || null,
        sawPrice: listing.price,
        specCount: Object.keys(listing.specs || {}).length,
        galleryImages: (listing.imageUrls || []).length,
        url: location.href,
      });
      return null;
    }

    const payload = {
      platform: "shopee",
      itemId: listing.itemId,
      shopId: listing.shopId,
      title: listing.title,
      price: listing.price,
      originalPrice: listing.originalPrice,
      sellerRating: listing.sellerRating,
      shopLocation: listing.shopLocation,
      specs: listing.specs,
      imageUrls: listing.imageUrls,
      reviewImageUrls: listing.reviewImageUrls,
      reviews: reviewData.reviews,
      reviewStats: reviewData.reviewStats,
      _source: listing.source,
    };

    const s = reviewData.reviewStats;
    console.info(
      `[Sentinel] read listing via ${listing.source}:`,
      `"${listing.title.slice(0, 50)}"`,
      `$${listing.price}`,
      `${payload.imageUrls.length} gallery / ${payload.reviewImageUrls.length} review images`,
      s
        ? `${s.usable}/${s.totalFound} reviews usable (${s.discardedTooShort} too short)`
        : "no reviews"
    );
    return payload;
  }

  root.Sentinel.extract = { parseProductUrl, extractListing, fromDom };
})(typeof self !== "undefined" ? self : globalThis);
