export function GET() {
  return Response.json({
    url: (process.env.NEXT_PUBLIC_SUPABASE_URL || '').trim().replace(/\/$/,''),
    key: (process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY || '').trim(),
    bank: (process.env.TRIPFACT_DEPOSIT_ACCOUNT || '').trim(),
  }, {headers: {'Cache-Control':'no-store'}});
}
