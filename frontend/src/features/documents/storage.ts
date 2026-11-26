export interface SavedDocument {
  owner: string;
  id: string;
  file: File;
  thumbnail: Blob | null;
  createdAt: number;
}

async function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("ilera-documents", 1);
    request.onupgradeneeded = () => {
      const files = request.result.createObjectStore("files", { keyPath: ["owner", "id"] });
      files.createIndex("by-owner", "owner");
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function transact<T>(mode: IDBTransactionMode, action: (files: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await openDatabase();
  try {
    return await new Promise((resolve, reject) => {
      const transaction = db.transaction("files", mode);
      const request = action(transaction.objectStore("files"));
      transaction.oncomplete = () => resolve(request.result);
      transaction.onabort = () => reject(transaction.error);
    });
  } finally {
    db.close();
  }
}

export async function listDocuments(owner: string): Promise<SavedDocument[]> {
  const files = await transact<SavedDocument[]>("readonly", (store) => store.index("by-owner").getAll(owner));
  return files.sort((a, b) => b.createdAt - a.createdAt);
}

export async function saveDocument(file: SavedDocument): Promise<void> {
  await transact("readwrite", (store) => store.add(file));
}

export async function deleteDocument(owner: string, id: string): Promise<void> {
  await transact("readwrite", (store) => store.delete([owner, id]));
}
