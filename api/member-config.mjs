export function GET() {
  return Response.json({
    url: process.env.NEXT_PUBLIC_SUPABASE_URL || '',
    key: process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY || '',
    bank: process.env.TRIPFACT_DEPOSIT_ACCOUNT || '',
  }, {headers: {'Cache-Control':'no-store'}});
}
