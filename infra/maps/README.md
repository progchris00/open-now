# Philippines PMTiles on Cloudflare R2

The application reads one public PMTiles archive directly in the browser. No
map API key is used.

## Upload

Choose a dated URL from the [Protomaps basemap builds](https://maps.protomaps.com/builds/)
and extract the Philippines region with the PMTiles CLI:

```sh
pmtiles extract "$PROTOMAPS_BUILD_URL" philippines.pmtiles --bbox=116.8,4.5,127,21.5
pmtiles verify philippines.pmtiles
```

Authenticate Wrangler with a Cloudflare account that can write to the target
R2 bucket, then run:

```sh
PMTILES_FILE=/path/to/philippines.pmtiles \
R2_BUCKET=openow-maps \
R2_OBJECT_KEY=philippines.pmtiles \
./infra/maps/upload_pmtiles.sh
```

Apply the CORS example with
`wrangler r2 bucket cors set "$R2_BUCKET" --file infra/maps/cors.example.json`
after adjusting the origins to match the app. An `r2.dev` public URL is suitable for local
development only. Production should use an R2 custom domain.

Set `MAP_TILES_URL` to the public HTTPS object URL. The Next.js server reads
this setting at request time and passes it to the client map component.
With Compose, set the variable in the root `.env`, recreate the web service
with `docker compose up -d web`, then open
`http://localhost:8080/delivery-details`. Confirm the browser receives
`206 Partial Content` for archive range requests and the marker can be moved.
