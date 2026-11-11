const locations = {
  center: [16.0678, 108.2208],
  beach: [16.0536, 108.2479],
  bana: [15.9953, 107.9967],
  hoian: [15.877, 108.328],
};

export async function GET(request) {
  const area = new URL(request.url).searchParams.get('area') || 'center';
  if (!Object.hasOwn(locations, area)) return Response.json({error:'unknown_area'}, {status:400});
  const key = process.env.GOOGLE_WEATHER_API_KEY;
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
    if (!response.ok) return Response.json({error:'weather_unavailable'}, {status:502});
    const result = await response.json();
    const days = (result.forecastDays || []).map(day => {
      const {year, month, day:date} = day.displayDate;
      return {
        date: [year, String(month).padStart(2, '0'), String(date).padStart(2, '0')].join('-'),
        max: day.maxTemperature?.degrees ?? null,
        min: day.minTemperature?.degrees ?? null,
        rain: day.daytimeForecast?.precipitation?.probability?.percent ?? null,
        condition: day.daytimeForecast?.weatherCondition?.description?.text || '',
      };
    });
    if (!days.length) return Response.json({error:'weather_unavailable'}, {status:502});
    return Response.json({days}, {headers:{'Cache-Control':'no-store'}});
  } catch {
    return Response.json({error:'weather_unavailable'}, {status:502});
  }
}
