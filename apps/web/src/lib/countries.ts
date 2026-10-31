/** Country name (as stored on investors) -> ISO 3166 alpha-2, for flags. */
const ISO: Record<string, string> = {
  "United States": "US", "United Kingdom": "GB", Germany: "DE", France: "FR", Canada: "CA", India: "IN", Israel: "IL",
  Spain: "ES", Australia: "AU", Sweden: "SE", Switzerland: "CH", Singapore: "SG", Italy: "IT", Belgium: "BE",
  Finland: "FI", Brazil: "BR", China: "CN", Japan: "JP", Denmark: "DK", "United Arab Emirates": "AE", Norway: "NO",
  Poland: "PL", Portugal: "PT", Mexico: "MX", Ireland: "IE", "New Zealand": "NZ", Austria: "AT", Turkey: "TR",
  "South Africa": "ZA", "Czech Republic": "CZ", Estonia: "EE", Argentina: "AR", Indonesia: "ID", Hungary: "HU",
  Taiwan: "TW", Luxembourg: "LU", Greece: "GR", "Saudi Arabia": "SA", Romania: "RO", Ukraine: "UA", Malaysia: "MY",
  Chile: "CL", Russia: "RU", Thailand: "TH", Kenya: "KE", Monaco: "MC", Colombia: "CO", Lithuania: "LT",
  Bulgaria: "BG", Philippines: "PH", Latvia: "LV", Uruguay: "UY", Vietnam: "VN", Cyprus: "CY", Netherlands: "NL",
  "The Netherlands": "NL", Nigeria: "NG", Egypt: "EG", Bangladesh: "BD", Iceland: "IS", Panama: "PA", Slovakia: "SK",
  Kazakhstan: "KZ", Slovenia: "SI", Malta: "MT", "Costa Rica": "CR", Armenia: "AM", "Sri Lanka": "LK", Ecuador: "EC",
  Guatemala: "GT", Mauritius: "MU", Rwanda: "RW", Georgia: "GE", Madagascar: "MG", "El Salvador": "SV",
  Tanzania: "TZ", Peru: "PE", Barbados: "BB", Azerbaijan: "AZ", Oman: "OM", Tunisia: "TN", Mauritania: "MR",
  "Dominican Republic": "DO", Ghana: "GH", Paraguay: "PY", Qatar: "QA", Morocco: "MA", Belarus: "BY", Kuwait: "KW",
  Serbia: "RS", Pakistan: "PK", "Trinidad And Tobago": "TT", Andorra: "AD", "South Korea": "KR", "Hong Kong": "HK",
  Croatia: "HR", Bahrain: "BH", Jordan: "JO", Lebanon: "LB", Uganda: "UG", Ethiopia: "ET",
};

export const SHORT: Record<string, string> = { "United States": "USA", "United Kingdom": "UK", "United Arab Emirates": "UAE", "The Netherlands": "Netherlands" };

export function flag(country?: string): string {
  const code = country ? ISO[country] : undefined;
  if (!code) return "";
  return String.fromCodePoint(...[...code].map((c) => 0x1f1e6 + c.charCodeAt(0) - 65));
}
