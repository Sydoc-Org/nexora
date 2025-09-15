// js:

async function toggleDetailsAndLoadImages(event) {
    // ... (your existing code to show/hide the row)

    // ... (try/catch block)

    imageContainer.innerHTML = ''; 
    imageContainer.style.display = 'flex';
    imageContainer.style.flexWrap = 'wrap';
    imageContainer.style.gap = '1rem'; 

    // **CHANGE**: Fire off all image loads at once without awaiting each one
    const imagePromises = [];
    for (let i = 0; i < imageCount; i++) {
        // We push the promise to an array, but don't wait for it here
        imagePromises.push(loadImage(imageContainer, workitemid, i));
    }
    
    // Optional: If you need to do something after ALL images have attempted to load
    // await Promise.all(imagePromises);
    // console.log("All images have finished loading or failed.");

    // ... (end of try/catch)
}