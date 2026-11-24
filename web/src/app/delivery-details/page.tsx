import { connection } from "next/server";

import { DeliveryDetailsScreen } from "../../components/map/DeliveryDetailsScreen";


export default async function DeliveryDetailsPage() {
  await connection();
  return (
    <DeliveryDetailsScreen tilesUrl={process.env.MAP_TILES_URL?.trim() ?? ""} />
  );
}
