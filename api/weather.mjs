const cityLocations = {danang: {
  center: [16.0678, 108.2208],
  beach: [16.0536, 108.2479],
  bana: [15.9953, 107.9967],
  hoian: [15.877, 108.328],
},nhatrang:{center:[12.2388,109.1967],hontre:[12.2167,109.2667],camranh:[11.99556,109.21833]},phuquoc:{center:[10.2167,103.9667],north:[10.327,103.858],south:[10.029,104.004],airport:[10.1698,103.9935],onglang:[10.27,103.927],saobeach:[10.057,104.034],khembeach:[10.034,104.031]}};

export async function GET(request) {
  const query=new URL(request.url).searchParams;
  const city=query.get('city')||'danang';
  if(!Object.hasOwn(cityLocations,city))return Response.json({error:'unknown_city'},{status:400});
  const locations=cityLocations[city];
  const area = query.get('area') || 'center';
  if (!Object.hasOwn(locations, area)) return Response.json({error:'unknown_area'}, {status:400});
  const key = process.env.GOOGLE_WEATHER_API_KEY?.trim();
  if (!key) return Response.json({error:'not_configured'}, {status:503});

  const [latitude, longitude] = locations[area];
  const url = new URL('https://weather.googleapis.com/v1/forecast/days:lookup');
  url.search = new URLSearchParams({
    'location.latitude': String(latitude), 'location.longitude': String(longitude),
    days:'7', pageSize:'7', unitsSystem:'METRIC', languageCode:'ko',
  });
  try {
    const response = await fetch(url, {
      headers: {'X-Goog-Api-Key': key},
      signal: AbortSignal.timeout(6000),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      const reason = body?.error?.details?.find(detail => detail.domain === 'googleapis.com')?.reason;
      console.warn('[weather] Google request failed', {
        status: response.status,
        reason: typeof reason === 'string' && /^[A-Z0-9_]{1,80}$/.test(reason) ? reason : 'unknown',
      });
      return Response.json({error:'weather_unavailable'}, {status:502});
    }
    const result = await response.json();
    const days = (result.forecastDays || []).map(day => {
      const {year, month, day:date} = day.displayDate;
      return {
        date: [year, String(month).padStart(2, '0'), String(date).padStart(2, '0')].join('-'),
        max: day.maxTemperature?.degrees ?? null,
        min: day.minTemperature?.degrees ?? null,
        rain: day.daytimeForecast?.precipitation?.probability?.percent ?? null,
        condition: day.daytimeForecast?.weatherCondition?.description?.text || '',
        conditionType: day.daytimeForecast?.weatherCondition?.type || '',
        iconBaseUri: day.daytimeForecast?.weatherCondition?.iconBaseUri || '',
      };
    });
    if (!days.length) {
      console.warn('[weather] Google returned no forecast days');
      return Response.json({error:'weather_unavailable'}, {status:502});
    }
    return Response.json({days}, {headers:{'Cache-Control':'no-store'}});
  } catch (error) {
    console.warn('[weather]', error?.name === 'TimeoutError' ? 'Google request timed out' : 'Google request or response processing failed');
    return Response.json({error:'weather_unavailable'}, {status:502});
  }
}
