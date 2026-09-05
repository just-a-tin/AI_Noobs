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

  // --- Layer 2: DOM fallback -----------------------------------------------

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

  /**
   * Find SGD amounts by text shape, then take the most prominent.
   *
   * Scans ELEMENTS, not text nodes. Shopee renders the currency symbol in its
   * own element (`<span>$</span><span>12.90</span>`), so no single text node
   * ever contains "$12.90" and a text-node scan silently finds no price at
   * all. An element's textContent joins its children back together.
   */
  function scrapePrices() {
    // Optional decimals: Shopee shows whole-dollar prices without them.
    const priceRe = /(?:S\$|SGD|\$)\s?([\d,]+(?:\.\d{1,2})?)/;
    const found = [];

    for (const el of document.body.querySelectorAll("*")) {
      const text = (el.textContent || "").trim();
      // Keep it tight: a match on a wrapper div would inherit the whole page.
      if (!text || text.length > 30) continue;

      const m = priceRe.exec(text);
      if (!m) continue;

      const value = parseFloat(m[1].replace(/,/g, ""));
      if (!Number.isFinite(value) || value <= 0) continue;

      const style = getComputedStyle(el);
      if (style.display === "none" || style.visibility === "hidden") continue;

      found.push({
        value,
        size: parseFloat(style.fontSize) || 0,
        struck: /line-through/.test(style.textDecorationLine),
        textLen: text.length,
      });
    }

    if (!found.length) return { price: null, originalPrice: null };

    // Nested elements each match, so prefer the innermost (shortest text) at
    // a given font size — that is the price itself, not its container.
    const rank = (a, b) => b.size - a.size || a.textLen - b.textLen;

    const current = found.filter((f) => !f.struck).sort(rank)[0];
    const original = found
      .filter((f) => f.struck)
      .sort((a, b) => b.value - a.value)[0];

    const price = current ? current.value : found.sort(rank)[0].value;
    return {
      price,
      // A struck-through price below the current one is not a discount.
      originalPrice: original && original.value > price ? original.value : null,
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
    const reviewHeadingRe = /\b(review|rating|ulasan|penilaian)\b/i;
    let reviewAnchor = null;
    for (const el of document.querySelectorAll(
      "h1,h2,h3,h4,section,div[class],[role='heading']"
    )) {
      const own = (el.childElementCount ? "" : el.textContent || "").trim();
      if (own && own.length < 60 && reviewHeadingRe.test(own)) {
        reviewAnchor = el;
        break;
      }
    }

    const gallery = [];
    const review = [];
    const seen = new Set();

    for (const img of document.querySelectorAll("img")) {
      const src = img.currentSrc || img.src;
      if (!src || !src.includes("susercontent.com")) continue;
      // naturalWidth is 0 for images that have not loaded; only skip when we
      // positively know the image is icon-sized.
      if (img.naturalWidth && img.naturalWidth < 100) continue;

      const url = src.split("_tn")[0];
      if (seen.has(url)) continue;
      seen.add(url);

      const isAfterAnchor =
        reviewAnchor &&
        reviewAnchor.compareDocumentPosition(img) &
          Node.DOCUMENT_POSITION_FOLLOWING;

      (isAfterAnchor ? review : gallery).push(url);
    }

    return { gallery, review };
  }

  function fromDom({ itemId, shopId }) {
    const { price, originalPrice } = scrapePrices();
    const { gallery, review } = scrapeImages();
    return {
      source: "dom",
      itemId,
      shopId,
      title: scrapeTitle(),
      price,
      originalPrice,
      sellerRating: null,
      shopLocation: null,
      specs: scrapeSpecs(),
      imageUrls: gallery.slice(0, config.maxGalleryImages),
      reviewImageUrls: review.slice(0, config.maxReviewImages),
    };
  }

  // --- Orchestration --------------------------------------------------------

  async function extractListing() {
    const ids = parseProductUrl();
    if (!ids) return null;

    let listing = null;
    let apiError = null;
    try {
      listing = await fromPdpApi(ids);
    } catch (err) {
      // console.warn, not console.debug: Chrome hides Verbose messages by
      // default, so a debug-level failure log is invisible exactly when
      // someone is trying to work out why nothing happened.
      apiError = String(err?.message || err);
      console.warn("[Sentinel] PDP API unavailable, falling back to DOM:", apiError);
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

    if (!listing.title || listing.price == null) {
      // Say precisely which field is missing and what was seen, so a broken
      // page can be diagnosed from one pasted console line.
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
        reviewImages: (listing.reviewImageUrls || []).length,
        url: location.href,
      });
      return null;
    }

    console.info(
      `[Sentinel] read listing via ${listing.source}:`,
      `"${listing.title.slice(0, 60)}"`,
      `$${listing.price}`,
      `${listing.imageUrls.length} gallery / ${listing.reviewImageUrls.length} review images`
    );

    return {
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
      _source: listing.source,
    };
  }

  root.Sentinel.extract = { parseProductUrl, extractListing, fromDom };

  // Callable from DevTools (choose the "Sentinel" context in the console's
  // top-left dropdown) to see exactly what each layer found on this page.
  root.sentinelDebug = async function () {
    const ids = parseProductUrl();
    console.log("[Sentinel] url ids:", ids);
    if (!ids) return console.log("[Sentinel] not a product URL");

    try {
      console.log("[Sentinel] PDP API:", await fromPdpApi(ids));
    } catch (err) {
      console.log("[Sentinel] PDP API failed:", String(err));
    }
    console.log("[Sentinel] DOM scrape:", fromDom(ids));
    console.log("[Sentinel] final:", await extractListing());
  };
})(typeof self !== "undefined" ? self : globalThis);
