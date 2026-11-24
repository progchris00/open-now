"use client";

import { useState } from "react";

import { MapPin, type MapPoint } from "./MapPin";
import styles from "./delivery-details.module.css";


const MANILA: MapPoint = { latitude: 14.5995, longitude: 120.9842 };


type DeliveryDetailsScreenProps = {
  tilesUrl: string;
};


export function DeliveryDetailsScreen({ tilesUrl }: DeliveryDetailsScreenProps) {
  const [point, setPoint] = useState(MANILA);

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <p className={styles.eyebrow}>Delivery details</p>
        <h1>Where should we deliver?</h1>
        <p>
          Add your address, then drag the pin to the exact entrance the rider
          should use.
        </p>
      </header>
      <div className={styles.content}>
        <form
          aria-label="Delivery address"
          className={styles.form}
          onSubmit={(event) => event.preventDefault()}
        >
          <label>
            Full name
            <input autoComplete="name" name="name" required />
          </label>
          <label>
            Mobile number
            <input autoComplete="tel" inputMode="tel" name="phone" required />
          </label>
          <label>
            Street and building
            <input autoComplete="street-address" name="street" required />
          </label>
          <label>
            Barangay
            <input name="barangay" required />
          </label>
          <label>
            Delivery note
            <textarea name="note" rows={3} />
          </label>
          <p aria-live="polite" className={styles.coordinates}>
            Pin: {point.latitude.toFixed(5)}, {point.longitude.toFixed(5)}
          </p>
          <button type="submit" disabled>Save delivery address</button>
          <p className={styles.handoff}>
            This preview keeps the selected pin on this page. Address saving
            will be available in the next delivery-details update.
          </p>
        </form>
        <div className={styles.mapPanel}>
          <MapPin
            initialPoint={MANILA}
            onPointChange={setPoint}
            tilesUrl={tilesUrl}
          />
        </div>
      </div>
    </main>
  );
}
